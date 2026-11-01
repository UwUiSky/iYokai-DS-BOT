"""
core/desktop_staff.py
=====================
Pannello rapido dello staff di iYokai Desktop (SPEC D.9): il programma chiede, il **bot** agisce, dopo aver
controllato con i permessi veri della persona nel server. Azioni: blocca e sblocca un canale, timeout a un
membro, annuncio in un canale. Ogni richiesta lascia una riga in `desktop_azioni` e un motivo nel registro di
Discord. Il risultato è un codice breve: il programma lo traduce.
Funzioni coperte: SPEC D.9 (#108)
Dipende da: core/repositories/desktop_repo.py
"""

from __future__ import annotations

import logging
from datetime import timedelta

import discord

from core.repositories.desktop_repo import desktop_repo

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


async def esegui(bot, user_id: int, guild_id, azione, dati: dict) -> str:
    """Il codice dell'esito. Il server deve esistere e la persona esserci con il permesso per quell'azione."""
    guild = bot.get_guild(guild_id) if _intero(guild_id) else None
    if guild is None:
        return SERVER_SCONOSCIUTO
    if azione not in AZIONI:
        return AZIONE_SCONOSCIUTA
    membro = await _membro(guild, user_id)
    if membro is None:
        esito = NESSUN_PERMESSO
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
