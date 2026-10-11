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
mai nel nulla. Il primo decadimento di un utente arriva solo dopo una
settimana intera dalla sua prima riga.
Funzioni coperte: REVIEW.md LC-8 (errori isolati per server nel giro).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.guild_iteration import for_each_guild_safely
from core.leveling_logic import previous_week_start, week_key
from core.repositories.leveling_repo import leveling_repo

logger = logging.getLogger("iyokai.weekly_personal_decay_worker")

TICK_SECONDS = 3600


class WeeklyPersonalDecayWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)
        settimana_corrente = week_key(adesso)

        # Chi è arrivato dopo l'inizio della settimana scorsa non ha
        # ancora vissuto una settimana intera: niente decadimento.
        nati_prima_di = previous_week_start(adesso)
        server = await leveling_repo.list_guilds_needing_weekly_decay(
            settimana_corrente, created_before=nati_prima_di
        )

        async def _per_server(guild_id: int) -> None:
            # PERF-6: un solo UPDATE per server; le coin tolte arrivano
            # in cassa nella stessa transazione.
            utenti, tolti = await leveling_repo.apply_weekly_decay_guild(
                guild_id, settimana_corrente, nati_prima_di
            )
            logger.info(
                "Decadimento settimanale nel server %s: %s saldi, %s coin alla cassa.",
                guild_id, utenti, tolti,
            )

        # LC-8: un server problematico non blocca gli altri.
        await for_each_guild_safely(
            server, _per_server, nome_worker="Decadimento settimanale personale"
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
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Weekly personal decay worker avviato (controllo ogni %ds).", TICK_SECONDS)


weekly_personal_decay_worker = WeeklyPersonalDecayWorker()
