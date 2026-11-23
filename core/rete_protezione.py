"""
core/rete_protezione.py
=======================
Rete di protezione tra server (VER-025, D111, D112), il lavoro con Discord. Tre cose separate:
1) `segnala`: avviso agli owner (o al canale scelto) degli ALTRI server dove ci sono l'utente e il bot;
2) `compromesso`: timeout in TUTTI i server dove c'è l'utente, con caso scritto e avviso agli owner;
3) `dopo_ban`: rete facoltativa dei ban, con proposta a tasto o ban automatico, sempre annullabile.
Mai il contenuto dei messaggi né dati privati. Mai su proprietari dei server, mai sui bot. Le regole pure stanno in
core/rete_protezione_logic.py, i dati in core/repositories/rete_repo.py.
Funzioni coperte: SPEC §6.22 (VER-025)
Dipende da: core/rete_protezione_logic.py, core/repositories/rete_repo.py, core/repositories/moderation_repo.py
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import discord

from core import bot_roles
from core import rete_protezione_logic as lg
from core.bounded_cache import BoundedCache
from core.i18n import testo_guild
from core.repositories.moderation_repo import moderation_repo
from core.repositories.rete_repo import rete_repo

logger = logging.getLogger("iyokai.rete")

_serrature: BoundedCache[int, asyncio.Lock] = BoundedCache(5_000)  # un utente alla volta: l'allarme arriva a raffica
_ORIGINE_CASO = "rete"


@dataclass(frozen=True)
class Risultato:
    rifiuto: str | None = None
    consegnati: int = 0


def _serratura(user_id: int) -> asyncio.Lock:
    s = _serrature.get(user_id)
    if s is None:
        s = asyncio.Lock()
        _serrature.set(user_id, s)
    return s


def _adesso() -> datetime:
    return datetime.now(timezone.utc)


def _menzioni_spente() -> discord.AllowedMentions:
    return discord.AllowedMentions.none()


async def _manda_agli_owner(bot, guild: discord.Guild, impostazioni, *, embed: discord.Embed, view=None) -> bool:
    """Scrive nel canale scelto (se si può) altrimenti in privato al proprietario. False se non è arrivato a nessuno."""
    canale = guild.get_channel(impostazioni.canale_id) if impostazioni.canale_id else None
    if isinstance(canale, discord.TextChannel):
        permessi = canale.permissions_for(guild.me)
        if permessi.send_messages and permessi.embed_links:
            try:
                await canale.send(embed=embed, view=view, allowed_mentions=_menzioni_spente())
                return True
            except discord.HTTPException:
                logger.warning("Avviso della rete non scritto nel canale del server %s.", guild.id)
    try:
        proprietario = guild.owner or await bot.fetch_user(guild.owner_id)
        await proprietario.send(embed=embed, view=view, allowed_mentions=_menzioni_spente())
        return True
    except (discord.HTTPException, AttributeError):
        logger.warning("Avviso della rete non consegnato al proprietario del server %s.", guild.id)
        return False


# --- 1) avviso agli altri server ---------------------------------------
async def _embed_avviso(guild, user_id: int, categoria: str, gravita: str, quando: datetime, origine_nome: str | None) -> discord.Embed:
    cat = await testo_guild(guild, f"rete_cat_{categoria}")
    grav = await testo_guild(guild, f"rete_grav_{gravita}")
    embed = discord.Embed(
        title=await testo_guild(guild, "rete_avviso_titolo"),
        description=(await testo_guild(guild, "rete_avviso_corpo", utente=f"<@{user_id}>", id=user_id, categoria=cat, gravita=grav))[:4096],
        color=discord.Color.orange(), timestamp=quando,
    )
    if origine_nome:
        embed.add_field(name=await testo_guild(guild, "rete_avviso_origine"), value=discord.utils.escape_markdown(origine_nome)[:100], inline=False)
    embed.set_footer(text=(await testo_guild(guild, "rete_avviso_piede"))[:2048])
    return embed


async def segnala(
    bot, origine: discord.Guild, user_id: int, categoria: str, azione: str = "", *, repo=rete_repo, ora: datetime | None = None
) -> Risultato:
    """Avvisa gli altri server dove ci sono l'utente e il bot. Rifiuta (codice in `rifiuto`) se il server d'origine è piccolo,
    nuovo, bloccato o ha già fatto troppe segnalazioni, o se la stessa cosa è già stata segnalata oggi."""
    if categoria not in lg.CATEGORIE or user_id == getattr(bot.user, "id", None):
        return Risultato("categoria")
    ora = ora or _adesso()
    async with _serratura(user_id):
        rifiuto = lg.origine_puo_segnalare(
            origine.member_count or 0, getattr(origine.me, "joined_at", None), ora,
            await repo.e_bloccato(origine.id), await repo.segnalazioni_origine_oggi(origine.id),
        )
        if rifiuto:
            return Risultato(rifiuto)
        if await repo.gia_segnalato(user_id, categoria, lg.PAUSA_STESSO_UTENTE_ORE):
            return Risultato("gia_segnalato")
        gravita = lg.gravita_di(categoria, azione)
        segnalazione = await repo.registra_segnalazione(user_id, origine.id, categoria, gravita)
        nome_origine = origine.name if (await repo.impostazioni(origine.id)).mostra_origine else None
        consegnati = 0
        for guild in tuple(bot.guilds)[: lg.MAX_SERVER_PER_SEGNALAZIONE * 5]:
            if guild.id == origine.id or consegnati >= lg.MAX_SERVER_PER_SEGNALAZIONE:
                continue
            membro = guild.get_member(user_id)
            if membro is None or membro.bot or user_id == guild.owner_id:
                continue
            impostazioni = await repo.impostazioni(guild.id)
            if not lg.destinazione_puo_ricevere(impostazioni.ricezione, await repo.consegne_oggi(guild.id)):
                continue
            embed = await _embed_avviso(guild, user_id, categoria, gravita, ora, nome_origine)
            if await _manda_agli_owner(bot, guild, impostazioni, embed=embed):
                await repo.registra_consegna(segnalazione, guild.id)
                consegnati += 1
        return Risultato(None, consegnati)


# --- 2) account compromesso: timeout ovunque ----------------------------
async def compromesso(
    bot, user_id: int, origine_id: int | None, *, repo=rete_repo, ora: datetime | None = None, crea_vista=None,
    escludi: frozenset[int] = frozenset(),
) -> int:
    """Timeout in tutti i server dove c'è l'utente (gerarchia e permessi del bot rispettati in ognuno). Torna quanti server.
    `escludi`: server dove chi rileva ha già agito (per esempio l'AutoMod): lì non si mette un secondo timeout."""
    if user_id == getattr(bot.user, "id", None):
        return 0
    ora = ora or _adesso()
    colpiti = 0
    async with _serratura(user_id):
        for guild in tuple(bot.guilds):
            membro = guild.get_member(user_id)
            if membro is None or guild.id in escludi:
                continue
            rifiuto = lg.bot_puo_colpire(
                e_proprietario=membro.id == guild.owner_id, e_bot=membro.bot,
                e_il_nostro_bot=bot_roles.e_un_nostro_bot(membro.id, bot),
                bot_sopra=guild.me.top_role > membro.top_role,
                bot_ha_permesso=guild.me.guild_permissions.moderate_members,
            )
            if rifiuto or await repo.timeout_attivo(guild.id, user_id):
                continue
            impostazioni = await repo.impostazioni(guild.id)
            ore = lg.ore_timeout_valide(impostazioni.timeout_ore)
            fino_a = lg.timeout_fino_a(ora, ore)
            motivo = lg.motivo_rete("account_compromesso")
            try:
                await membro.timeout(fino_a, reason=motivo)
            except discord.HTTPException:
                logger.warning("Timeout della rete non messo nel server %s.", guild.id)
                continue
            try:
                caso = await moderation_repo.create_case(
                    guild.id, user_id, bot.user.id, "timeout", reason=motivo, duration_seconds=ore * 3600, origine=_ORIGINE_CASO
                )
            except Exception:  # noqa: BLE001  # il timeout c'è già: il caso mancato non lo toglie
                logger.warning("Caso della rete non scritto nel server %s.", guild.id)
                caso = None
            await repo.registra_timeout(guild.id, user_id, origine_id or 0, fino_a, caso)
            colpiti += 1
            embed = discord.Embed(
                title=await testo_guild(guild, "rete_compromesso_titolo"),
                description=(await testo_guild(guild, "rete_compromesso_corpo", utente=f"<@{user_id}>", id=user_id, ore=ore, caso=caso or 0))[:4096],
                color=discord.Color.red(), timestamp=ora,
            )
            vista = await crea_vista(guild, "to", guild.id, user_id) if crea_vista else None
            await _manda_agli_owner(bot, guild, impostazioni, embed=embed, view=vista)
    return colpiti


async def togli_timeout(bot, guild: discord.Guild, user_id: int, da: int, *, repo=rete_repo) -> bool:
    """Toglie il timeout messo dalla rete in un server. False se la rete non ne aveva messo uno ancora attivo.
    Chi può chiamarla (proprietario del server o del bot) lo decide chi chiama, ricontrollando al momento."""
    if not await repo.annulla_timeout(guild.id, user_id, da):
        return False
    membro = guild.get_member(user_id)
    if membro is not None:
        try:
            await membro.timeout(None, reason=f"Timeout della rete tolto da {da}"[:512])
        except discord.HTTPException:
            logger.warning("Timeout della rete non tolto su Discord nel server %s.", guild.id)
    return True


# --- 3) rete facoltativa dei ban -----------------------------------------
async def dopo_ban(
    bot, origine: discord.Guild, user_id: int, categoria: str, origine_caso: str, *, repo=rete_repo, crea_vista=None
) -> int:
    """Un server aderente ha bannato per un motivo grave: ogni altro aderente dove c'è l'utente riceve una proposta o il ban
    automatico. Un ban che viene dalla rete non ne fa partire altri (niente catene). Torna quanti server toccati."""
    if categoria not in lg.CATEGORIE:
        return 0
    aderenti = await repo.aderenti_ban()
    toccati = 0
    for guild in tuple(bot.guilds):
        rifiuto = lg.proposta_ammessa(
            origine=origine.id, destinazione=guild.id, origine_aderisce=origine.id in aderenti,
            dest_aderisce=guild.id in aderenti, origine_caso=origine_caso,
        )
        membro = guild.get_member(user_id)
        if rifiuto or membro is None or membro.bot or membro.id == guild.owner_id:
            continue
        proposta_id = await repo.crea_proposta(user_id, origine.id, guild.id, categoria)
        if proposta_id is None:
            continue
        toccati += 1
        if aderenti[guild.id] == "automatico":
            await applica_ban(bot, guild, proposta_id, None, repo=repo)
            continue
        impostazioni = await repo.impostazioni(guild.id)
        embed = discord.Embed(
            title=await testo_guild(guild, "rete_ban_proposta_titolo"),
            description=(await testo_guild(
                guild, "rete_ban_proposta_corpo", utente=f"<@{user_id}>", id=user_id, categoria=await testo_guild(guild, f"rete_cat_{categoria}")
            ))[:4096],
            color=discord.Color.orange(),
        )
        await _manda_agli_owner(bot, guild, impostazioni, embed=embed, view=await crea_vista(guild, "ap", proposta_id, 0) if crea_vista else None)
    return toccati


async def applica_ban(bot, guild: discord.Guild, proposta_id: int, deciso_da: int | None, *, repo=rete_repo) -> str:
    """Applica una proposta (a mano con il tasto, o in automatico). Codici: «ok», «gia_deciso», «gerarchia», «fallito».
    Lo stato passa da «proposta» una volta sola, PRIMA del ban: due tasti premuti insieme non bannano due volte."""
    proposta = await repo.proposta(proposta_id)
    if proposta is None or proposta["guild_dest"] != guild.id:
        return "gia_deciso"
    if not await repo.decidi(proposta_id, "proposta", "applicato", deciso_da):
        return "gia_deciso"
    user_id = proposta["user_id"]
    membro = guild.get_member(user_id)
    rifiuto = None
    if membro is not None:
        rifiuto = lg.bot_puo_colpire(
            e_proprietario=membro.id == guild.owner_id, e_bot=membro.bot, e_il_nostro_bot=bot_roles.e_un_nostro_bot(membro.id, bot),
            bot_sopra=guild.me.top_role > membro.top_role, bot_ha_permesso=guild.me.guild_permissions.ban_members,
        )
    elif not guild.me.guild_permissions.ban_members:
        rifiuto = "permesso"
    if rifiuto:
        await repo.decidi(proposta_id, "applicato", "fallito", deciso_da)
        return "gerarchia" if rifiuto == "gerarchia" else "fallito"
    motivo = f"Rete dei ban ({proposta['categoria']}): ban deciso in un altro server aderente"[:512]
    try:
        await guild.ban(discord.Object(id=user_id), reason=motivo, delete_message_seconds=0)
    except discord.HTTPException:
        await repo.decidi(proposta_id, "applicato", "fallito", deciso_da)
        return "fallito"
    try:
        caso = await moderation_repo.create_case(guild.id, user_id, bot.user.id, "ban", reason=motivo, origine=_ORIGINE_CASO)
    except Exception:  # noqa: BLE001  # il ban c'è già: il caso mancato non lo toglie
        logger.warning("Caso del ban di rete non scritto nel server %s.", guild.id)
        caso = None
    await repo.decidi(proposta_id, "applicato", "applicato", deciso_da, caso)
    if deciso_da is None:  # automatico: lo staff lo viene a sapere
        embed = discord.Embed(
            title=await testo_guild(guild, "rete_ban_auto_titolo"),
            description=(await testo_guild(guild, "rete_ban_auto_corpo", utente=f"<@{user_id}>", id=user_id, caso=caso or 0))[:4096],
            color=discord.Color.red(),
        )
        await _manda_agli_owner(bot, guild, await repo.impostazioni(guild.id), embed=embed)
    return "ok"


async def annulla_ban(bot, guild: discord.Guild, proposta_id: int, da: int, *, repo=rete_repo) -> bool:
    """Toglie il ban messo dalla rete (unban + caso revocato). False se la proposta non è un ban applicato qui."""
    proposta = await repo.proposta(proposta_id)
    if proposta is None or proposta["guild_dest"] != guild.id or proposta["stato"] != "applicato":
        return False
    if not await repo.decidi(proposta_id, "applicato", "annullato", da):
        return False
    try:
        await guild.unban(discord.Object(id=proposta["user_id"]), reason=f"Ban della rete annullato da {da}"[:512])
    except discord.NotFound:
        pass  # già tolto a mano
    except discord.HTTPException:
        await repo.decidi(proposta_id, "annullato", "applicato", da)  # non riuscito: resta com'era
        return False
    if proposta["case_number"]:
        await moderation_repo.revoke_case(guild.id, proposta["case_number"], da)
    return True


async def rifiuta_proposta(proposta_id: int, guild_id: int, da: int, *, repo=rete_repo) -> bool:
    proposta = await repo.proposta(proposta_id)
    if proposta is None or proposta["guild_dest"] != guild_id:
        return False
    return await repo.decidi(proposta_id, "proposta", "rifiutato", da)


# --- punti di ingresso per chi rileva (AutoMod, anti-nuke, casi) ----------
_in_corso: set[asyncio.Task] = set()


def _in_sottofondo(coro) -> asyncio.Task:
    compito = asyncio.create_task(coro)
    _in_corso.add(compito)
    compito.add_done_callback(_in_corso.discard)
    return compito


async def _compromesso_con_tasti(bot, user_id: int, origine_id: int | None, escludi: frozenset[int]) -> int:
    from core.rete_protezione_vista import crea_vista

    try:
        return await compromesso(bot, user_id, origine_id, crea_vista=crea_vista, escludi=escludi)
    except Exception:  # noqa: BLE001  # la rete non deve mai far cadere chi rileva
        logger.warning("Rete: timeout per account compromesso non completato.", exc_info=False)
        return 0


def avvia_compromesso(bot, user_id: int, origine_id: int | None, escludi=()) -> asyncio.Task:
    """Chiamata da AutoMod e anti-nuke quando un account sembra compromesso: il lavoro (molti server) va in sottofondo.
    `escludi`: i server dove chi rileva ha già agito."""
    return _in_sottofondo(_compromesso_con_tasti(bot, user_id, origine_id, frozenset(escludi)))


async def _dopo_caso(bot, guild_id: int, user_id: int, azione: str, origine: str, motivo: str | None) -> None:
    from core.rete_protezione_vista import crea_vista

    guild = bot.get_guild(guild_id)
    categoria = lg.categoria_da_motivo(motivo)
    if guild is None or categoria is None or origine == _ORIGINE_CASO or azione not in lg.AZIONI_CHE_SEGNALANO:
        return
    try:
        await segnala(bot, guild, user_id, categoria, azione)
        if azione == "ban":
            await dopo_ban(bot, guild, user_id, categoria, origine, crea_vista=crea_vista)
        if categoria == "account_compromesso":
            await compromesso(bot, user_id, guild_id, crea_vista=crea_vista, escludi=frozenset({guild_id}))
    except Exception:  # noqa: BLE001
        logger.warning("Rete: caso del server %s non gestito.", guild_id, exc_info=False)


def ascoltatore_casi(bot):
    """L'ascoltatore da registrare in core/caso_eventi.py: ogni nuovo caso grave arriva qui."""

    async def _su_caso(guild_id, case_number, user_id, moderator_id, action_type, origine, motivo):
        await _dopo_caso(bot, guild_id, user_id, action_type, origine, motivo)

    return _su_caso
