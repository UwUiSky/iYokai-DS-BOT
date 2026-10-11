"""
core/security_quarantine.py
===========================
Il ruolo "Quarantined" e le operazioni su chi ci sta dentro, condivise
dall'anti-raid (un sospetto raider appena entrato) e dall'anti-nuke
(l'autore di un attacco, SIC-002).

Il ruolo ha un'esistenza sola per server: la ricerca-o-creazione sta
dietro un blocco per server, cosi' ingressi o attacchi simultanei non
ne creano due. Ogni canale nega al ruolo scrittura, thread, reazioni e
voce; i canali creati dopo ricevono lo stesso blocco (listener
dell'anti-raid).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import weakref
from dataclasses import dataclass, field

import discord

from core.bounded_cache import BoundedCache
from core.permission_risk_logic import critical_permissions_of
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_logic import ALL_NUKE_CATEGORIES, bot_role_problems
from core.security_rate_tracker import security_rate_tracker

logger = logging.getLogger("iyokai.security_quarantine")

NOME_RUOLO_QUARANTENA = "Quarantined"

# Cosa non puo' fare chi e' in quarantena. I thread ereditano dal canale
# che li contiene; la chat di un vocale e' coperta da send_messages.
PERMESSI_QUARANTENA = {
    "send_messages": False,
    "send_messages_in_threads": False,
    "create_public_threads": False,
    "create_private_threads": False,
    "add_reactions": False,
    "speak": False,
    "connect": False,
}

# Dal 16/11/2026 un canale che il bot non puo' vedere arriva con questo
# nome finto (LIMITI.md, Parte 2): non va toccato.
NOME_CANALE_NASCOSTO = "___hidden___"

MAX_SERVER_CON_BLOCCO = 5000
# Un asyncio.Lock vale per un solo ciclo di eventi: i blocchi stanno
# dietro il ciclo che li ha creati (nel bot ce n'e' uno; nei test uno
# per prova).
_blocchi: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, BoundedCache[int, asyncio.Lock]]" = (
    weakref.WeakKeyDictionary()
)


def _blocco(guild_id: int) -> asyncio.Lock:
    ciclo = asyncio.get_running_loop()
    per_server = _blocchi.get(ciclo)
    if per_server is None:
        per_server = BoundedCache(max_size=MAX_SERVER_CON_BLOCCO)
        _blocchi[ciclo] = per_server
    blocco = per_server.get(guild_id)
    if blocco is None:
        blocco = asyncio.Lock()
        per_server.set(guild_id, blocco)
    return blocco


def allinea_necessario(channel: discord.abc.GuildChannel, role: discord.Role) -> bool:
    """True se il canale non nega ancora al ruolo tutti i permessi di quarantena."""
    if channel.name == NOME_CANALE_NASCOSTO:
        return False
    permessi = channel.overwrites_for(role)
    return not all(getattr(permessi, nome) is False for nome in PERMESSI_QUARANTENA)


async def blocca_canale(channel: discord.abc.GuildChannel, role: discord.Role) -> None:
    """
    Nega al ruolo di quarantena scrittura, thread, reazioni e voce su
    un canale. Gli stessi permessi valgono per ogni tipo di canale: quelli
    che non c'entrano con quel tipo non hanno effetto. Un canale che
    rifiuta la modifica non ferma gli altri.
    """
    if channel.name == NOME_CANALE_NASCOSTO:
        return
    try:
        await channel.set_permissions(
            role, reason="Anti-Raid: blocco del ruolo di quarantena", **PERMESSI_QUARANTENA
        )
    except discord.HTTPException:
        logger.warning(
            "Impossibile impostare l'overwrite quarantena sul canale %s (server %s).",
            channel.id, channel.guild.id,
        )


async def _senza_permessi(role: discord.Role) -> None:
    """Un ruolo di quarantena con permessi darebbe poteri a chi e' in quarantena (SIC-004)."""
    if role.permissions.value == 0:
        return
    try:
        await role.edit(
            permissions=discord.Permissions.none(),
            reason="Anti-Raid: il ruolo di quarantena non può avere permessi",
        )
    except discord.HTTPException:
        logger.warning("Impossibile azzerare i permessi del ruolo di quarantena %s.", role.id)


async def _trova_o_crea(
    guild: discord.Guild, settings: SecuritySettings
) -> tuple[discord.Role | None, bool]:
    """
    (ruolo, creato_adesso): un ruolo appena creato ha gia' i permessi su
    ogni canale, uno trovato no. Va chiamata dentro il blocco del server.
    """
    if settings.quarantine_role_id is not None:
        role = guild.get_role(settings.quarantine_role_id)
        if role is not None:
            await _senza_permessi(role)
            return role, False

    # Un ruolo "Quarantined" gia' nel server (fatto a mano o da una
    # versione precedente) si usa, invece di crearne un secondo.
    esistente = discord.utils.get(guild.roles, name=NOME_RUOLO_QUARANTENA)
    if esistente is not None and not esistente.managed:
        await _senza_permessi(esistente)
        await security_repo.save_settings(
            dataclasses.replace(settings, quarantine_role_id=esistente.id)
        )
        return esistente, False

    try:
        role = await guild.create_role(
            name=NOME_RUOLO_QUARANTENA,
            reason="Ruolo di quarantena creato automaticamente da iYokai (Anti-Raid)",
        )
    except discord.HTTPException as errore:
        logger.warning(
            "Impossibile creare il ruolo di quarantena nel server %s: %s", guild.id, errore
        )
        return None, False

    for channel in guild.channels:
        await blocca_canale(channel, role)

    await security_repo.save_settings(dataclasses.replace(settings, quarantine_role_id=role.id))
    return role, True


async def ruolo_quarantena(guild: discord.Guild, *, allinea: bool = True) -> discord.Role | None:
    """
    Il ruolo di quarantena del server, creato se manca. Con piu' chiamate
    insieme la prima crea il ruolo, le altre aspettano e lo trovano gia'
    salvato. Con `allinea` i canali che non negano ancora i permessi di
    quarantena a un ruolo trovato (non creato adesso) vengono sistemati:
    chi chiama spesso lo chiede una volta sola per server.
    """
    async with _blocco(guild.id):
        settings = await security_repo.get_settings(guild.id)
        ruolo, creato = await _trova_o_crea(guild, settings)
        if ruolo is not None and not creato and allinea:
            for canale in guild.channels:
                if allinea_necessario(canale, ruolo):
                    await blocca_canale(canale, ruolo)
        return ruolo


@dataclass(frozen=True)
class EsitoQuarantena:
    """
    Cosa e' successo davvero. `in_quarantena`: il ruolo e' stato dato.
    `ruoli_non_tolti`: si voleva togliere anche il potere e non e' riuscito
    (di solito un ruolo sopra a quello del bot): chi e' dentro e' ancora
    potente e chi riferisce l'esito non deve dire "messo in quarantena" e basta.
    """

    in_quarantena: bool
    ruoli_tolti: list[int] = field(default_factory=list)
    ruoli_non_tolti: bool = False

    @property
    def completo(self) -> bool:
        return self.in_quarantena and not self.ruoli_non_tolti


async def metti_in_quarantena(
    member: discord.Member, reason: str, *, togli_ruoli: bool
) -> EsitoQuarantena:
    """
    Mette `member` nel ruolo di quarantena. Con `togli_ruoli` gli toglie
    anche gli altri ruoli (tranne quelli gestiti da Discord) e ne
    restituisce gli ID, cosi' si possono rimettere al rilascio.
    Se il server non permette di togliere i ruoli, almeno aggiunge la
    quarantena, ma lo dice: `ruoli_non_tolti`.
    """
    guild = member.guild
    ruolo = await ruolo_quarantena(guild)
    if ruolo is None:
        return EsitoQuarantena(False)
    reason = reason[:512]

    non_tolti = False
    if togli_ruoli:
        tolti = [r for r in member.roles if not r.managed and not r.is_default() and r.id != ruolo.id]
        restano = [r for r in member.roles if r.managed and not r.is_default()]
        try:
            await member.edit(roles=restano + [ruolo], reason=reason)
            return EsitoQuarantena(True, [r.id for r in tolti])
        except discord.HTTPException:
            logger.warning("Quarantena: impossibile togliere i ruoli a %s, aggiungo solo il ruolo.", member.id)
            non_tolti = True

    try:
        await member.add_roles(ruolo, reason=reason)
    except discord.HTTPException:
        return EsitoQuarantena(False, ruoli_non_tolti=non_tolti)
    return EsitoQuarantena(True, ruoli_non_tolti=non_tolti)


@dataclass(frozen=True)
class EsitoRilascio:
    riuscito: bool
    # Ruoli del caso che non si sono potuti rimettere (cancellati, gestiti, sopra al bot).
    saltati: tuple[int, ...] = ()
    # Altri casi attivi dello stesso utente: la quarantena resta finche' ci sono.
    altri_casi: tuple[int, ...] = ()
    quarantena_tenuta: bool = False


def azzera_contatori(guild_id: int, user_id: int, tracker=None) -> None:
    """Dopo un rilascio l'utente riparte da zero: i conteggi vecchi non lo ripuniscono subito."""
    categorie = tuple(ALL_NUKE_CATEGORIES) + tuple(f"{c}:ora" for c in ALL_NUKE_CATEGORIES)
    (tracker or security_rate_tracker).forget(guild_id, user_id, categorie)


async def rilascia_utente(
    member: discord.Member, *, caso_numero: int | None, reason: str
) -> EsitoRilascio:
    """
    L'unico modo di liberare qualcuno dalla quarantena (anti-nuke e
    anti-raid usano questo). Con un caso rimette i ruoli di QUEL caso e lo
    segna rilasciato; senza, toglie solo la quarantena. Se l'utente ha altri
    casi attivi la quarantena resta: ogni caso va rilasciato da se'.
    """
    guild = member.guild
    settings = await security_repo.get_settings(guild.id)
    ruolo = guild.get_role(settings.quarantine_role_id) if settings.quarantine_role_id else None
    caso = await security_repo.get_nuke_case(guild.id, caso_numero) if caso_numero is not None else None
    altri = tuple(
        c.case_number for c in await security_repo.active_cases_for_actor(guild.id, member.id)
        if c.case_number != caso_numero
    )
    tieni = ruolo is not None and bool(altri)

    saltati: list[int] = []
    da_rimettere: list[discord.Role] = []
    for role_id in (caso.removed_role_ids if caso else ()):
        role = guild.get_role(role_id)
        if role is None or role.managed or role.is_default() or role >= guild.me.top_role:
            saltati.append(role_id)
        else:
            da_rimettere.append(role)

    reason = reason[:512]
    try:
        if da_rimettere:
            attuali = [
                r for r in member.roles
                if not r.is_default() and (ruolo is None or tieni or r.id != ruolo.id)
            ]
            await member.edit(roles=attuali + [r for r in da_rimettere if r not in attuali], reason=reason)
        elif ruolo is not None and ruolo in member.roles and not tieni:
            await member.remove_roles(ruolo, reason=reason)
    except discord.HTTPException:
        return EsitoRilascio(False, tuple(saltati), altri, tieni)

    if caso is not None:
        await security_repo.mark_nuke_case_released(guild.id, caso.case_number)
    return EsitoRilascio(True, tuple(saltati), altri, tieni)


def problemi_ruoli_del_bot(guild: discord.Guild, quarantine_role_id: int | None) -> tuple[str, ...]:
    """
    SIC-022: cosa, nei ruoli del server, impedisce al bot di fermare un
    attacco (permesso mancante, ruolo di quarantena o ruoli pericolosi
    sopra al suo). Frasi pronte da mostrare.
    """
    me = guild.me
    quarantena = guild.get_role(quarantine_role_id) if quarantine_role_id else None
    propri = {r.id for r in me.roles}
    sopra = max(
        (
            r.position for r in guild.roles
            if not r.managed and not r.is_default() and r.id not in propri
            and critical_permissions_of(dict(r.permissions))
        ),
        default=0,
    )
    return bot_role_problems(
        has_manage_roles=me.guild_permissions.manage_roles or me.guild_permissions.administrator,
        bot_top_position=me.top_role.position,
        quarantine_role_position=quarantena.position if quarantena else None,
        highest_staff_position=sopra,
    )
