"""
core/event_log_retention.py
==============================
Pulizia periodica del log eventi unificato (BACKLOG.md §3): elimina
le voci più vecchie della retention di ciascun server (30 giorni
Free, 180 Premium — core/event_log_retention_logic.py), una volta al
giorno. Stesso pattern architetturale di core/memory_guard.py: una
classe con un tasks.loop periodico, avviata una volta da main.py, non
un Cog con comandi.

A differenza di Memory Guard (un solo controllo bot-wide), qui la
retention è PER SERVER — ogni server può essere Free o Premium
indipendentemente — quindi il tick itera bot.guilds e controlla lo
stato premium di ciascuno prima di decidere la soglia da applicare.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from discord.ext import commands, tasks

from core.event_log_retention_logic import retention_days_for
from core.premium import guild_has_premium_access
from core.repositories.event_log_repo import event_log_repo
from cogs.logging.basic_logs import MODULE_LOGGING

logger = logging.getLogger("iyokai.event_log_retention")

TICK_SECONDS = 24 * 3600  # una volta al giorno: la retention si misura in giorni, non serve più spesso


class EventLogRetentionService:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot) -> None:
        now = datetime.now(timezone.utc)
        totale_eliminati = 0

        for guild in bot.guilds:
            is_premium = await guild_has_premium_access(guild.id, MODULE_LOGGING)
            giorni = retention_days_for(is_premium)
            soglia = now - timedelta(days=giorni)

            # prune_old_events_for_guild, non prune_old_events: la
            # soglia cambia da server a server (Free/Premium), quindi
            # va applicata una guild alla volta, non globalmente.
            eliminati = await event_log_repo.prune_old_events_for_guild(guild.id, soglia)
            totale_eliminati += eliminati

        if totale_eliminati > 0:
            logger.info(
                "Retention log eventi: %d voci eliminate su %d server.",
                totale_eliminati,
                len(bot.guilds),
            )

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick della retention del log eventi")

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info("Retention del log eventi avviata (controllo ogni %ds).", TICK_SECONDS)


# Istanza unica, condivisa da tutto il progetto — coerente con
# core/memory_guard.py, core/scheduler.py, core/database.py.
event_log_retention = EventLogRetentionService()
