"""
core/guild_clan_treasury_decay_worker.py
============================================
Servizio periodico che applica il decadimento mensile del 10% sulla
tesoreria NON SPESA dei clan (SPEC.md §15.14) — stesso pattern di
core/monthly_winners_announcer.py: tick orario, idempotente tramite
last_decay_period salvato sul clan (un solo decadimento per mese
anche con riavvii del bot o più tick nello stesso giorno).

Le coin rimosse dal decadimento confluiscono nella cassa del server
a cui appartiene il clan (SPEC.md §15.15, core.repositories.
guild_chest_repo) — stessa destinazione del decadimento settimanale
sui coin personali (core.weekly_personal_decay_worker), non svaniscono
mai nel nulla.
Funzioni coperte: REVIEW.md LC-8 (errori isolati per server nel giro).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.guild_iteration import for_each_guild_safely
from core.leveling_logic import period_key
from core.repositories.guild_chest_repo import (
    REASON_MONTHLY_CLAN_DECAY,
    guild_chest_repo,
)
from core.repositories.guild_clan_repo import guild_clan_repo

logger = logging.getLogger("iyokai.guild_clan_treasury_decay_worker")

TICK_SECONDS = 3600


class GuildClanTreasuryDecayWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)
        periodo_corrente = period_key(adesso)

        async def _per_clan(clan) -> None:
            if clan.last_decay_period == periodo_corrente:
                return  # già applicato questo mese

            saldo_prima, saldo_dopo = await guild_clan_repo.apply_monthly_decay(
                clan.id, periodo_corrente
            )
            delta = saldo_prima - saldo_dopo
            if delta > 0:
                await guild_chest_repo.deposit(
                    clan.guild_id, delta, REASON_MONTHLY_CLAN_DECAY
                )
            logger.info(
                "Decadimento mensile applicato al clan %s: %s -> %s.",
                clan.id, saldo_prima, saldo_dopo,
            )

        # LC-8: un clan problematico non blocca gli altri.
        await for_each_guild_safely(
            await guild_clan_repo.list_officialized_clans(),
            _per_clan,
            nome_worker="Decadimento mensile tesoreria clan",
        )

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick()
            except Exception:
                logger.exception("Errore nel tick del decadimento mensile tesoreria clan")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Guild clan treasury decay worker avviato (controllo ogni %ds).", TICK_SECONDS)


guild_clan_treasury_decay_worker = GuildClanTreasuryDecayWorker()
