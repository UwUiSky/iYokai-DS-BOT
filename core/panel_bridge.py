"""
core/panel_bridge.py
====================
Il ponte tra il pannello web e il bot. Il pannello gira nello stesso
processo del bot: legge i server dalla memoria del bot, controlla i
permessi a ogni richiesta e scrive SOLO dai punti unici dei comandi
(D16: `core.config_schema`, `core.command_access.imposta_ruolo`).
Le cache del database si svuotano a ogni scrittura: il bot vede subito
il cambio, senza riavvio.
Funzioni coperte: SPEC §24.1–24.4, §24.7 (NF-20, issue #91; NF-22, #93)
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

import discord

from core.command_access import (
    Livello,
    RuoloAdminNegato,
    TipoRuolo,
    decidi_accesso,
    imposta_ruolo,
    leggi_ruolo,
)
from core.command_search_logic import ComandoInfo, raccogli_comandi
from core.config import config
from core.config_history_logic import TIPI_MODIFICA
from core.config_schema import ImpostazioneNonValida, imposta_lingua_server, imposta_modulo
from core.database import db
from core.premium import registry

logger = logging.getLogger("iyokai.panel_bridge")

MAX_RUOLI_MOSTRATI = 250
MAX_STORICO = 100
_DURATA_CACHE_COMANDI = 300.0
# Membri chiesti a Discord (non nella memoria del bot): tenuti poco, così ogni
# clic non diventa una chiamata all'API, ma un permesso tolto vale entro 30 secondi.
DURATA_CACHE_MEMBRI = 30.0
MAX_CACHE_MEMBRI = 1000
_cache_membri: OrderedDict[tuple[int, int], tuple[float, discord.Member | None]] = OrderedDict()

ETICHETTE_RUOLI = {
    TipoRuolo.ADMIN: "Ruolo admin del bot",
    TipoRuolo.MOD: "Ruolo mod del bot",
    TipoRuolo.MODBAN: "Ruolo ban del bot",
}


# ---------------------------------------------------------------- permessi
async def _membro(guild: discord.Guild, user_id: int, *, chiedi_a_discord: bool) -> discord.Member | None:
    membro = guild.get_member(user_id)
    if membro is not None or not chiedi_a_discord:
        return membro
    chiave = (guild.id, user_id)
    adesso = time.monotonic()
    salvato = _cache_membri.get(chiave)
    if salvato is not None and salvato[0] > adesso:
        return salvato[1]
    try:
        membro = await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        membro = None
    _cache_membri.pop(chiave, None)
    _cache_membri[chiave] = (adesso + DURATA_CACHE_MEMBRI, membro)
    while len(_cache_membri) > MAX_CACHE_MEMBRI:
        _cache_membri.popitem(last=False)
    return membro


async def puo_gestire(guild: discord.Guild, user_id: int, *, chiedi_a_discord: bool = True) -> bool:
    """
    Stessa regola dei comandi di `/admin` (Livello.ADMIN): «Gestisci server»,
    il ruolo admin del bot o il proprietario del server. Si controlla a ogni
    richiesta, con lo stato attuale del server.
    """
    membro = await _membro(guild, user_id, chiedi_a_discord=chiedi_a_discord)
    if membro is None:
        return False
    ruolo_admin = await leggi_ruolo(guild.id, TipoRuolo.ADMIN)
    return decidi_accesso(
        Livello.ADMIN,
        user_id=user_id,
        owner_bot_id=config.OWNER_ID,
        guild_owner_id=guild.owner_id,
        permessi=membro.guild_permissions,
        ruoli_utente_ids=[r.id for r in membro.roles],
        ruolo_configurato_id=ruolo_admin,
        ruolo_esiste=ruolo_admin is not None and guild.get_role(ruolo_admin) is not None,
    )


async def server_gestibile(bot, guild_id: int, user_id: int) -> discord.Guild | None:
    """Il server, solo se il bot c'è e l'utente lo può gestire adesso."""
    guild = bot.get_guild(guild_id)
    if guild is None or not await puo_gestire(guild, user_id):
        return None
    return guild


async def server_gestibili(bot, user_id: int) -> list[discord.Guild]:
    """I server dove il bot c'è e l'utente può gestirli (solo dalla memoria del bot)."""
    risultato = []
    for guild in bot.guilds:
        if await puo_gestire(guild, user_id, chiedi_a_discord=False):
            risultato.append(guild)
    return sorted(risultato, key=lambda g: g.name.lower())


# ----------------------------------------------------------------- lettura
async def stato_server(guild: discord.Guild) -> dict:
    """Moduli (per categoria), ruoli del bot e lingua del server."""
    moduli = []
    for modulo in registry.all_modules():
        moduli.append(
            {
                "nome": modulo.name,
                "titolo": modulo.display_name,
                "descrizione": modulo.description,
                "categoria": modulo.category,
                "premium": registry.is_module_premium(modulo.name),
                "attivo": await db.is_module_active_for_guild(guild.id, modulo.name),
            }
        )
    ruoli_bot = [
        {"tipo": tipo.name.lower(), "etichetta": ETICHETTE_RUOLI[tipo], "attuale": await leggi_ruolo(guild.id, tipo)}
        for tipo in TipoRuolo
    ]
    ruoli_server = [
        {"id": r.id, "nome": r.name}
        for r in sorted(guild.roles, key=lambda r: -r.position)
        if r.id != guild.id and not r.managed
    ][:MAX_RUOLI_MOSTRATI]
    return {
        "moduli": moduli,
        "ruoli_bot": ruoli_bot,
        "ruoli_server": ruoli_server,
        "lingua": await db.get_guild_language(guild.id),
    }


async def storico(guild_id: int, tipo: str | None = None) -> list:
    """Le ultime modifiche (comandi e pannello insieme: lo storico è uno solo)."""
    tipo = tipo if tipo in TIPI_MODIFICA else None
    return await db.get_config_history_filtrato(guild_id, limit=MAX_STORICO, change_type=tipo)


async def stato_premium(bot, guild: discord.Guild) -> dict:
    """Le stesse righe di `/admin premium stato`, più il link al negozio di Discord."""
    from cogs.utility.premium_server import url_negozio
    from core.premium import get_guild_premium_breakdown
    from core.premium_status_logic import righe_stato_server
    from core.repositories.module_subscription_repo import module_subscription_repo

    dettaglio = await get_guild_premium_breakdown(guild.id, bot=bot)
    scadenze = [
        f"{s.module_name} fino al {s.expires_at.date().isoformat()}"
        for s in await module_subscription_repo.list_for_guild(guild.id)
    ]
    return {
        "righe": righe_stato_server(dettaglio, scadenze),
        "alpha": bool(config.PREMIUM_ALPHA_UNLOCK_ALL),
        "negozio": url_negozio(getattr(bot, "application_id", None)),
    }


_cache_comandi: tuple[float, int, list[ComandoInfo]] | None = None


def comandi_del_bot(bot) -> list[ComandoInfo]:
    """L'albero dei comandi (la stessa fonte della ricerca dei comandi nel bot), in memoria per 5 minuti."""
    global _cache_comandi
    adesso = time.monotonic()
    if _cache_comandi is not None and _cache_comandi[1] == id(bot) and _cache_comandi[0] > adesso:
        return _cache_comandi[2]
    comandi = sorted(raccogli_comandi(bot.tree.get_commands()), key=lambda c: c.percorso)
    _cache_comandi = (adesso + _DURATA_CACHE_COMANDI, id(bot), comandi)
    return comandi


# ---------------------------------------------------------------- scrittura
async def applica_modulo(bot, guild: discord.Guild, nome: str, attivo: bool, user_id: int) -> bool:
    return await imposta_modulo(bot, guild.id, nome, attivo, user_id)


async def applica_lingua(guild: discord.Guild, codice: str, user_id: int) -> str:
    return await imposta_lingua_server(guild.id, codice, user_id)


async def applica_ruolo(guild: discord.Guild, tipo_nome: str, ruolo_id: int | None, user_id: int) -> None:
    """
    `tipo_nome`: admin, mod o modban. `ruolo_id` None toglie il ruolo.
    Il ruolo admin nuovo richiede «Amministratore» o il proprietario (D28).
    """
    try:
        tipo = TipoRuolo[tipo_nome.upper()]
    except KeyError:
        raise ImpostazioneNonValida("Tipo di ruolo non valido.") from None
    ruolo = None
    if ruolo_id is not None:
        ruolo = guild.get_role(ruolo_id)
        if ruolo is None or ruolo.managed:
            raise ImpostazioneNonValida("Questo ruolo non esiste in questo server.")
    try:
        await imposta_ruolo(
            guild, tipo, ruolo, changed_by=user_id, autore=await _membro(guild, user_id, chiedi_a_discord=True)
        )
    except RuoloAdminNegato:
        raise
    except ValueError as errore:
        raise ImpostazioneNonValida(str(errore)) from None
