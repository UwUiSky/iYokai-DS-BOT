"""
core/economia_registro.py
=========================
Il canale con il registro dei movimenti di monete (ECO-006, D121). Non scrive un messaggio per movimento: ogni
minuto manda un solo riepilogo dei movimenti nuovi dello storico (ECO-007), al massimo 300 per giro e 20 righe per
messaggio. Quello che avanza resta per il giro dopo. Non racconta i movimenti passati all'attivazione né quelli
fatti dallo staff (non sono nello storico). Menzioni spente; il motivo è ripulito.
Funzioni coperte: ECO-006
Dipende da: core/bot_ready.py, tabella economia_movimenti (0685)
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.database import db
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.economia_registro")

TICK_SECONDS = 60
MAX_PER_GIRO = 300
RIGHE_MOSTRATE = 20
MAX_TESTO = 3900


def _pulito(motivo: str) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(motivo))[:30]


def riepilogo(righe: list[tuple[int, int, int, str]]) -> str:
    """Testo del lotto: totali e le prime righe. Ogni riga è (id, utente, delta, motivo)."""
    entrate = sum(d for _, _, d, _ in righe if d > 0)
    uscite = sum(d for _, _, d, _ in righe if d < 0)
    testo = [f"{len(righe)} movimenti: **+{entrate}** / **{uscite}**", ""]
    for _, utente, delta, motivo in righe[:RIGHE_MOSTRATE]:
        testo.append(f"<@{utente}> {delta:+d} · {_pulito(motivo)}")
    if len(righe) > RIGHE_MOSTRATE:
        testo.append(f"… e altri {len(righe) - RIGHE_MOSTRATE}")
    return "\n".join(testo)[:MAX_TESTO]


async def imposta(guild_id: int, channel_id: int) -> None:
    """Accende il registro: parte dai movimenti di adesso in poi."""
    await db.pool.execute(
        "INSERT INTO economia_registro_conf (guild_id, channel_id, ultimo_id) "
        "VALUES ($1, $2, COALESCE((SELECT MAX(id) FROM economia_movimenti WHERE guild_id = $1), 0)) "
        "ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id",
        guild_id, channel_id,
    )


async def togli(guild_id: int) -> bool:
    return (await db.pool.execute("DELETE FROM economia_registro_conf WHERE guild_id = $1", guild_id)).endswith(" 1")


async def tick(bot: commands.Bot) -> None:
    """Un giro: per ogni server con il registro acceso, un riepilogo dei movimenti nuovi."""
    for conf in await db.pool.fetch("SELECT guild_id, channel_id, ultimo_id FROM economia_registro_conf"):
        try:
            await _giro(bot, conf["guild_id"], conf["channel_id"], conf["ultimo_id"])
        except Exception:
            logger.exception("Registro dell'economia non scritto (server %s).", conf["guild_id"])


async def _giro(bot: commands.Bot, guild_id: int, channel_id: int, ultimo_id: int) -> None:
    righe = await db.pool.fetch(
        "SELECT id, user_id, delta, motivo FROM economia_movimenti WHERE guild_id = $1 AND id > $2 ORDER BY id LIMIT $3",
        guild_id, ultimo_id, MAX_PER_GIRO,
    )
    if not righe:
        return
    guild = bot.get_guild(guild_id)
    canale = guild.get_channel(channel_id) if guild else None
    if not isinstance(canale, discord.TextChannel):
        return
    permessi = canale.permissions_for(guild.me)
    if not (permessi.view_channel and permessi.send_messages and permessi.embed_links):
        return  # il lotto resta: si riprova al giro dopo
    lotto = [(r["id"], r["user_id"], r["delta"], r["motivo"]) for r in righe]
    embed = discord.Embed(title="Registro dei movimenti di monete", description=riepilogo(lotto), color=discord.Color.dark_gold())
    try:
        await canale.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning("Registro dell'economia non inviato (server %s).", guild_id)
        return
    await db.pool.execute("UPDATE economia_registro_conf SET ultimo_id = $2 WHERE guild_id = $1", guild_id, lotto[-1][0])


_loop_task: tasks.Loop | None = None


def start(bot: commands.Bot) -> None:
    global _loop_task
    if _loop_task is not None:
        return

    @giro_periodico(seconds=TICK_SECONDS)
    async def _loop():
        await tick(bot)

    @_loop.before_loop
    async def _before():
        await attendi_bot_pronto(bot)

    _loop_task = _loop
    _loop.start()
