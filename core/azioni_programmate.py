"""
core/azioni_programmate.py
==========================
Azioni sicure fatte più tardi (UTL-111, D121): fino a 5 per server, da un minuto a 30 giorni, scelte dall'elenco chiuso
di `core/azioni_sicure.py` (dare o togliere un ruolo, scrivere un messaggio, sbloccare un canale). Il momento lo tiene lo
scheduler; qui c'è l'elenco nel database. Quando scatta, l'azione si «prende» cancellando la riga (un secondo tentativo
dello scheduler non rifà niente) e i permessi di chi l'ha messa si rileggono in quel momento.
Funzioni coperte: UTL-111
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import discord

from core import azioni_sicure
from core.database import db
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.azioni_programmate")

AZIONE_SCHEDULER = "azione_programmata"
MIN_ATTESA = timedelta(minutes=1)
MAX_ATTESA = timedelta(days=30)


class TroppeProgrammate(Exception):
    """Il server ha già 5 azioni programmate."""


class AttesaNonValida(ValueError):
    """Da 1 minuto a 30 giorni."""


async def programma(guild_id: int, user_id: int, azione: azioni_sicure.Azione, attesa: timedelta) -> int:
    if azione.tipo not in azioni_sicure.TIPI_PROGRAMMATE:
        raise azioni_sicure.AzioneNonValida("tipo non ammesso")
    if not MIN_ATTESA <= attesa <= MAX_ATTESA:
        raise AttesaNonValida()
    quando = datetime.now(timezone.utc) + attesa
    async with db.pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('azioni_programmate'), $1)", guild_id % 2**31)
        if await conn.fetchval("SELECT count(*) FROM azioni_programmate WHERE guild_id = $1", guild_id) >= azioni_sicure.MAX_PROGRAMMATE:
            raise TroppeProgrammate()
        nuovo = await conn.fetchval(
            "INSERT INTO azioni_programmate (guild_id, user_id, azione, quando) VALUES ($1, $2, $3::jsonb, $4) RETURNING id",
            guild_id, user_id, json.dumps(azioni_sicure.a_dict(azione)), quando,
        )
    await scheduler.schedule(guild_id, user_id, AZIONE_SCHEDULER, quando, {"id": nuovo})
    return nuovo


async def elenco(guild_id: int):
    return await db.pool.fetch(
        "SELECT id, user_id, azione, quando FROM azioni_programmate WHERE guild_id = $1 ORDER BY quando", guild_id
    )


async def togli(guild_id: int, numero_id: int) -> bool:
    """Toglie un'azione dall'elenco; quando lo scheduler arriva, non trova niente da fare."""
    return (await db.pool.execute("DELETE FROM azioni_programmate WHERE guild_id = $1 AND id = $2", guild_id, numero_id)).endswith(" 1")


async def alla_scadenza(bot: discord.Client, guild_id: int, user_id: int, payload: dict) -> str | None:
    """Handler dello scheduler. Prende la riga (una volta sola) e fa l'azione. Restituisce il motivo se non è andata."""
    guild = bot.get_guild(guild_id)
    if guild is None:
        return "server non raggiungibile"  # la riga resta: lo scheduler riprova
    riga = await db.pool.fetchrow(
        "DELETE FROM azioni_programmate WHERE id = $1 AND guild_id = $2 RETURNING azione, user_id",
        int(payload.get("id", 0)), guild_id,
    )
    if riga is None:
        return None  # tolta o già fatta
    dati = json.loads(riga["azione"]) if isinstance(riga["azione"], str) else dict(riga["azione"])
    try:
        azione = azioni_sicure.da_dict(dati, ammessi=azioni_sicure.TIPI_PROGRAMMATE)
    except azioni_sicure.AzioneNonValida as errore:
        return str(errore)
    esecutore = guild.get_member(riga["user_id"])
    bersaglio = guild.get_member(azione.utente_id) if azione.utente_id else None
    motivo = await azioni_sicure.esegui(guild, azione, esecutore=esecutore, bersaglio=bersaglio, autonomo=True)
    if motivo:
        logger.info("Azione programmata non fatta (server %s): %s", guild_id, motivo)
    return motivo
