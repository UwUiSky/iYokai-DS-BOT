"""
core/weekly_personal_decay_worker.py
========================================
Servizio periodico che applica il decadimento SETTIMANALE del 10%
sui coin PERSONALI di QUALUNQUE membro con un saldo in
`leveling_totals` — in un clan o no (SPEC.md §15.15, richiesta
esplicita dell'utente, distinto dal decadimento MENSILE sulla
tesoreria di clan gestito da core.guild_clan_treasury_decay_worker).
Stesso pattern di quel worker e di core.monthly_winners_announcer:
tick orario, idempotente tramite last_weekly_decay_period salvato
per riga (un solo decadimento a settimana anche con riavvii del bot
o più tick nello stesso giorno).

Le coin rimosse dal decadimento confluiscono nella cassa del server
di appartenenza (core.repositories.guild_chest_repo) — non svaniscono
mai nel nulla.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from discord.ext import commands, tasks

from core.leveling_logic import week_key
from core.repositories.guild_chest_repo import (
    REASON_WEEKLY_PERSONAL_DECAY,
    guild_chest_repo,
)
from core.repositories.leveling_repo import leveling_repo

logger = logging.getLogger("iyokai.weekly_personal_decay_worker")

TICK_SECONDS = 3600


class WeeklyPersonalDecayWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)
        settimana_corrente = week_key(adesso)

        da_decadere = await leveling_repo.list_users_needing_weekly_decay(
            settimana_corrente
        )
        for guild_id, user_id in da_decadere:
            saldo_prima, saldo_dopo = await leveling_repo.apply_weekly_decay(
                guild_id, user_id, settimana_corrente
            )
            delta = saldo_prima - saldo_dopo
            if delta > 0:
                await guild_chest_repo.deposit(
                    guild_id, delta, REASON_WEEKLY_PERSONAL_DECAY
                )
            logger.info(
                "Decadimento settimanale applicato a %s/%s: %s -> %s.",
                guild_id, user_id, saldo_prima, saldo_dopo,
            )

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick()
            except Exception:
                logger.exception("Errore nel tick del decadimento settimanale personale")

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info("Weekly personal decay worker avviato (controllo ogni %ds).", TICK_SECONDS)


weekly_personal_decay_worker = WeeklyPersonalDecayWorker()
