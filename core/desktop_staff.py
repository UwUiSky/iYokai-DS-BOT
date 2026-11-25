"""
core/desktop_staff.py
=====================
Pannello rapido dello staff di iYokai Desktop (SPEC D.9): il programma chiede, il **bot** agisce, dopo aver
controllato con i permessi veri della persona nel server. Azioni: blocca e sblocca un canale, timeout a un
membro, annuncio in un canale. Prima di agire passa dagli stessi controlli dei comandi (modulo acceso, politica dei
comandi del server, panico); un timeout scrive anche il caso di moderazione. Ogni richiesta lascia una riga in
`desktop_azioni` e un motivo nel registro di Discord. Il risultato è un codice breve: il programma lo traduce.
Funzioni coperte: SPEC D.9 (#108)
Dipende da: core/repositories/desktop_repo.py, core/web_panel_accesso.py (politica dei comandi), core/panel_bridge.py
"""

from __future__ import annotations

import logging
from datetime import timedelta

import discord

from core.repositories.desktop_repo import desktop_repo
from core.repositories.moderation_repo import moderation_repo

logger = logging.getLogger("iyokai.desktop")

AZIONI = ("blocca_canale", "sblocca_canale", "timeout", "annuncio")
MAX_MINUTI_TIMEOUT = 40_320  # 28 giorni, il massimo di Discord
MAX_MOTIVO = 200
MAX_ANNUNCIO = 2000
NESSUNA_MENZIONE = discord.AllowedMentions.none()

OK = "ok"
SERVER_SCONOSCIUTO = "server_sconosciuto"
AZIONE_SCONOSCIUTA = "azione_sconosciuta"
DATI_NON_VALIDI = "dati_non_validi"
NESSUN_PERMESSO = "nessun_permesso"
CANALE_SCONOSCIUTO = "canale_sconosciuto"
MEMBRO_SCONOSCIUTO = "membro_sconosciuto"
GERARCHIA = "gerarchia"
BOT_SENZA_PERMESSI = "bot_senza_permessi"
MODULO_SPENTO = "modulo_spento"  # il modulo del comando corrispondente è spento nel server
POLITICA = "politica_comandi"  # la politica dei comandi del server vieta quell'azione a questa persona
PANICO = "server_in_panico"  # durante il panico decidono solo il proprietario e i fidati

# Ogni azione ha il suo comando e il suo modulo: i controlli sono gli stessi di quel comando.
PERCORSO_COMANDO = {
    "blocca_canale": "mod-canali lock", "sblocca_canale": "mod-canali unlock",
    "timeout": "mod-sanzioni timeout", "annuncio": None,
}
MODULO_COMANDO = {
    "blocca_canale": "moderation_channel_control", "sblocca_canale": "moderation_channel_control",
    "timeout": "moderation_actions", "annuncio": None,
}


def _intero(valore) -> int | None:
    return valore if isinstance(valore, int) and not isinstance(valore, bool) and valore > 0 else None


async def _membro(guild: discord.Guild, user_id: int) -> discord.Member | None:
    membro = guild.get_member(user_id)
    if membro is not None:
        return membro
    try:
        return await guild.fetch_member(user_id)
    except discord.HTTPException:
        return None


def _riassunto(azione: str, dati: dict) -> str:
    """Il dettaglio da conservare: ids e durata, mai il testo dell'annuncio."""
    pezzi = [f"{k}={str(dati[k])[:20]}" for k in ("channel_id", "target_id", "minuti") if k in dati]
    return azione + (" " + " ".join(pezzi) if pezzi else "")


async def _blocca(guild, membro, dati, bloccare: bool) -> str:
    canale = guild.get_channel(_intero(dati.get("channel_id")) or 0)
    if canale is None or not hasattr(canale, "set_permissions"):
        return CANALE_SCONOSCIUTO
    if not canale.permissions_for(membro).manage_channels:
        return NESSUN_PERMESSO
    permessi = canale.overwrites_for(guild.default_role)
    permessi.send_messages = False if bloccare else None
    try:
        await canale.set_permissions(
            guild.default_role, overwrite=permessi, reason=f"iYokai Desktop ({membro.id}): "
            + ("blocco" if bloccare else "sblocco")
        )
    except discord.Forbidden:
        return BOT_SENZA_PERMESSI
    return OK


async def _timeout(guild, membro, dati) -> str:
    target_id, minuti = _intero(dati.get("target_id")), _intero(dati.get("minuti"))
    motivo = str(dati.get("motivo", "")).strip()[:MAX_MOTIVO]
    if target_id is None or minuti is None or minuti > MAX_MINUTI_TIMEOUT:
        return DATI_NON_VALIDI
    if not membro.guild_permissions.moderate_members and not membro.guild_permissions.administrator:
        return NESSUN_PERMESSO
    bersaglio = await _membro(guild, target_id)
    if bersaglio is None:
        return MEMBRO_SCONOSCIUTO
    protetto = bersaglio.id == guild.owner_id or bersaglio.guild_permissions.administrator
    if protetto or (membro.id != guild.owner_id and bersaglio.top_role >= membro.top_role):
        return GERARCHIA
    try:
        await bersaglio.timeout(timedelta(minutes=minuti), reason=f"iYokai Desktop ({membro.id}): {motivo}"[:480])
    except discord.Forbidden:
        return BOT_SENZA_PERMESSI
    # Come /mod-sanzioni timeout: il timeout ha il suo caso, con chi l'ha deciso.
    try:
        await moderation_repo.create_case(
            guild_id=guild.id, user_id=bersaglio.id, moderator_id=membro.id, action_type="timeout",
            reason=f"iYokai Desktop: {motivo}"[:512] if motivo else "iYokai Desktop", duration_seconds=minuti * 60,
        )
    except Exception:  # noqa: BLE001 - il timeout c'è già: il caso mancato non lo toglie
        logger.warning("Caso del timeout da Desktop non scritto nel server %s.", guild.id, exc_info=True)
    return OK


async def _annuncio(guild, membro, dati) -> str:
    canale = guild.get_channel(_intero(dati.get("channel_id")) or 0)
    testo = str(dati.get("testo", "")).strip()
    if not testo or len(testo) > MAX_ANNUNCIO:
        return DATI_NON_VALIDI
    if canale is None or not hasattr(canale, "send"):
        return CANALE_SCONOSCIUTO
    permessi = canale.permissions_for(membro)
    if not (permessi.send_messages and permessi.manage_messages):
        return NESSUN_PERMESSO
    try:
        await canale.send(testo, allowed_mentions=NESSUNA_MENZIONE)
    except discord.Forbidden:
        return BOT_SENZA_PERMESSI
    return OK


async def _controlli_del_comando(guild: discord.Guild, membro: discord.Member, azione: str) -> str | None:
    """
    Gli stessi cancelli del comando vero: modulo acceso, panico, politica dei comandi del server (comando spento,
    ruoli richiesti o ignorati). Codice del rifiuto, o None. Mai un'eccezione: nel dubbio si rifiuta.
    """
    from core import lockdown_service, panel_bridge, web_panel_accesso
    from core.database import db
    from core.lockdown_logic import puo_agire_in_panico
    from core.repositories.security_repo import security_repo

    try:
        modulo = MODULO_COMANDO[azione]
        if modulo is not None and not await db.is_module_active_for_guild(guild.id, modulo):
            return MODULO_SPENTO
        if lockdown_service.panico_riservato(guild.id):
            impostazioni = await security_repo.get_settings(guild.id)
            if not puo_agire_in_panico(membro.id, guild.owner_id, impostazioni.anti_nuke):
                return PANICO
        if await web_panel_accesso.policy_blocca(
            guild, membro, PERCORSO_COMANDO[azione], esente=panel_bridge.e_esente_politica(guild, membro, membro.id)
        ):
            return POLITICA
    except Exception:  # noqa: BLE001 - un controllo che non si riesce a fare non è un via libera
        logger.warning("Controlli del comando non eseguibili per l'azione %s nel server %s.", azione, guild.id, exc_info=True)
        return NESSUN_PERMESSO
    return None


async def esegui(bot, user_id: int, guild_id, azione, dati: dict) -> str:
    """Il codice dell'esito. Il server deve esistere e la persona esserci con il permesso per quell'azione."""
    guild = bot.get_guild(guild_id) if _intero(guild_id) else None
    if guild is None:
        return SERVER_SCONOSCIUTO
    if azione not in AZIONI:
        return AZIONE_SCONOSCIUTA
    membro = await _membro(guild, user_id)
    rifiuto = await _controlli_del_comando(guild, membro, azione) if membro is not None else NESSUN_PERMESSO
    if rifiuto is not None:
        esito = rifiuto
    elif azione == "blocca_canale":
        esito = await _blocca(guild, membro, dati, True)
    elif azione == "sblocca_canale":
        esito = await _blocca(guild, membro, dati, False)
    elif azione == "timeout":
        esito = await _timeout(guild, membro, dati)
    else:
        esito = await _annuncio(guild, membro, dati)
    await desktop_repo.registra_azione(user_id, guild.id, azione, _riassunto(azione, dati), esito)
    return esito
