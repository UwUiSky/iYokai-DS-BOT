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

import discord

from core.bounded_cache import BoundedCache
from core.permission_risk_logic import critical_permissions_of
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_logic import bot_role_problems

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
            return role, False

    # Un ruolo "Quarantined" gia' nel server (fatto a mano o da una
    # versione precedente) si usa, invece di crearne un secondo.
    esistente = discord.utils.get(guild.roles, name=NOME_RUOLO_QUARANTENA)
    if esistente is not None and not esistente.managed:
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


async def metti_in_quarantena(
    member: discord.Member, reason: str, *, togli_ruoli: bool
) -> tuple[bool, list[int]]:
    """
    Mette `member` nel ruolo di quarantena. Con `togli_ruoli` gli toglie
    anche gli altri ruoli (tranne quelli gestiti da Discord) e ne
    restituisce gli ID, cosi' si possono rimettere al rilascio.
    Restituisce (riuscito, ID dei ruoli tolti). Se il server non
    permette di togliere i ruoli, almeno aggiunge la quarantena.
    """
    guild = member.guild
    ruolo = await ruolo_quarantena(guild)
    if ruolo is None:
        return False, []
    reason = reason[:512]

    if togli_ruoli:
        tolti = [r for r in member.roles if not r.managed and not r.is_default() and r.id != ruolo.id]
        restano = [r for r in member.roles if r.managed and not r.is_default()]
        try:
            await member.edit(roles=restano + [ruolo], reason=reason)
            return True, [r.id for r in tolti]
        except discord.HTTPException:
            logger.warning("Quarantena: impossibile togliere i ruoli a %s, aggiungo solo il ruolo.", member.id)

    try:
        await member.add_roles(ruolo, reason=reason)
        return True, []
    except discord.HTTPException:
        return False, []


async def rilascia_da_quarantena(
    member: discord.Member, ruoli_da_rimettere: tuple[int, ...], reason: str
) -> tuple[bool, list[int]]:
    """
    Toglie la quarantena e rimette i ruoli indicati (quelli che ancora
    esistono, non sono gestiti e stanno sotto il ruolo piu' alto del
    bot). Restituisce (riuscito, ID dei ruoli che non si sono potuti rimettere).
    """
    guild = member.guild
    settings = await security_repo.get_settings(guild.id)
    ruolo = guild.get_role(settings.quarantine_role_id) if settings.quarantine_role_id else None
    saltati: list[int] = []
    da_rimettere: list[discord.Role] = []
    for role_id in ruoli_da_rimettere:
        role = guild.get_role(role_id)
        if role is None or role.managed or role.is_default() or role >= guild.me.top_role:
            saltati.append(role_id)
        else:
            da_rimettere.append(role)

    attuali = [r for r in member.roles if not r.is_default() and (ruolo is None or r.id != ruolo.id)]
    nuovi = attuali + [r for r in da_rimettere if r not in attuali]
    try:
        await member.edit(roles=nuovi, reason=reason[:512])
    except discord.HTTPException:
        return False, saltati
    return True, saltati


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
