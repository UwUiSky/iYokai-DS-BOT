"""
core/backup_snapshot_worker.py
==============================
Loop settimanale che rifà lo snapshot utenti di ogni server main con un
backup attivo (membri non bot, verificati se c'è Verify Base). Il primo
giro aspetta che il bot sia pronto.
Funzioni coperte: SPEC §11.10
"""

from __future__ import annotations

import logging

from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.backup_snapshot_logic import is_eligible_for_snapshot
from core.repositories.backup_repo import backup_repo
from core.repositories.backup_user_snapshot_repo import backup_user_snapshot_repo
from core.repositories.verify_repo import verify_repo

logger = logging.getLogger("iyokai.backup_snapshot_worker")

TICK_SECONDS = 7 * 24 * 60 * 60  # settimanale


class BackupSnapshotWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, main_bot: commands.Bot) -> None:
        for main_guild_id in await backup_repo.get_all_main_guild_ids_with_backup():
            await self._snapshot_one_guild(main_bot, main_guild_id)

    async def _snapshot_one_guild(self, main_bot: commands.Bot, main_guild_id: int) -> None:
        guild = main_bot.get_guild(main_guild_id)
        if guild is None:
            logger.warning(
                "Snapshot settimanale saltato per il server %s: iYokai Main non ci risulta dentro.",
                main_guild_id,
            )
            return

        config_verify = await verify_repo.get_config(main_guild_id)
        verified_role_id = config_verify.verified_role_id if config_verify is not None else None

        membri_eleggibili = []
        for membro in guild.members:
            ruoli_id = {ruolo.id for ruolo in membro.roles}
            if is_eligible_for_snapshot(membro.bot, ruoli_id, verified_role_id):
                avatar_url = str(membro.display_avatar.url) if membro.display_avatar else None
                membri_eleggibili.append((membro.id, str(membro), avatar_url))

        await backup_user_snapshot_repo.save_snapshot(main_guild_id, membri_eleggibili)
        logger.info(
            "Snapshot settimanale completato per il server %s: %d utenti.",
            main_guild_id,
            len(membri_eleggibili),
        )

    def start(self, main_bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(main_bot)
            except Exception:
                logger.exception("Errore nel tick dello snapshot settimanale utenti")

        @_loop.before_loop
        async def _before():
            # Senza questa attesa il primo giro parte prima del login:
            # le guild sono vuote e lo snapshot salva 0 utenti.
            await attendi_bot_pronto(main_bot)

        self._loop_task = _loop
        self._loop_task.start()

    def stop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            self._loop_task = None


backup_snapshot_worker = BackupSnapshotWorker()
