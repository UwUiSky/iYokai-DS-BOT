"""
core/backup_queue_worker.py
===============================
Servizio periodico che elabora la coda dei job di backup (SPEC.md
§11.2) — stesso pattern architetturale di core/feed_watcher.py e
core/twitch_watcher.py: un tasks.loop periodico, avviato una volta
da main.py, non un Cog con comandi.

Un job alla volta (coda SERIALIZZATA, come richiesto esplicitamente
dallo schema): crea il server via Creator, clona tutto quello che si
può, poi manda all'amministratore del server principale l'URL da
cliccare per completare l'operazione (limite reale della piattaforma
Discord — un bot non può autoinvitarsi, vedi core/backup_
orchestrator.py).
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from core.backup_orchestrator import start_backup_job
from core.repositories.backup_repo import backup_repo

logger = logging.getLogger("iyokai.backup_queue_worker")

TICK_SECONDS = 60


class BackupQueueWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def _notifica_amministratore(self, main_guild: discord.Guild, url_invito: str) -> None:
        """
        DM al proprietario del server principale con l'URL da
        cliccare — un link che crea/trasferisce un intero server
        merita un messaggio privato, non un post in un canale
        qualsiasi. Se il DM fallisce (proprietario con i DM chiusi,
        non più raggiungibile, ecc.) logga soltanto — il job resta
        comunque 'completed' con il server creato e clonato, solo
        senza che nessuno abbia ancora ricevuto l'invito per
        completare il trasferimento; l'amministratore può comunque
        vedere l'esito con un comando apposito in futuro.
        """
        owner = main_guild.owner
        if owner is None:
            try:
                owner = await main_guild.fetch_member(main_guild.owner_id)
            except discord.HTTPException:
                owner = None

        if owner is None:
            logger.warning(
                "Impossibile trovare il proprietario del server %s per notificare il backup.",
                main_guild.id,
            )
            return

        embed = discord.Embed(
            title="📦 Backup pronto",
            description=(
                f"Il backup di **{main_guild.name}** è stato creato e popolato. "
                f"Clicca il link qui sotto per completare l'operazione (iYokai Main "
                f"deve entrare nel nuovo server prima che diventi utilizzabile):\n\n{url_invito}"
            ),
            color=discord.Color.blurple(),
        )
        try:
            await owner.send(embed=embed)
        except discord.HTTPException:
            logger.warning(
                "Impossibile mandare il DM di notifica backup al proprietario del server %s.",
                main_guild.id,
            )

    async def tick(
        self,
        creator_client: discord.Client,
        main_bot: commands.Bot,
        main_permissions: discord.Permissions,
    ) -> None:
        scaduti = await backup_repo.expire_stale_jobs()
        if scaduti:
            logger.info("%d job di backup scaduti (oltre 24h bloccati).", scaduti)

        job = await backup_repo.get_next_pending_job()
        if job is None:
            return

        await backup_repo.mark_running(job.id)

        main_guild = main_bot.get_guild(job.main_guild_id)
        if main_guild is None:
            await backup_repo.mark_failed(
                job.id, "iYokai Main non risulta essere nel server richiesto."
            )
            return

        try:
            nuovo_server, url_invito = await start_backup_job(
                creator_client, main_guild, main_bot.user.id, main_permissions
            )
        except Exception as exc:
            logger.exception("Job di backup #%s fallito durante la creazione/clonazione.", job.id)
            await backup_repo.mark_failed(job.id, str(exc))
            return

        await backup_repo.set_backup_guild_id(job.id, nuovo_server.id)
        await self._notifica_amministratore(main_guild, url_invito)

    def start(
        self,
        creator_client: discord.Client,
        main_bot: commands.Bot,
        main_permissions: discord.Permissions,
    ) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(creator_client, main_bot, main_permissions)
            except Exception:
                logger.exception("Errore nel tick del backup queue worker")

        @_loop.before_loop
        async def _before():
            await main_bot.wait_until_ready()
            await creator_client.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info("Backup queue worker avviato (controllo ogni %ds).", TICK_SECONDS)


backup_queue_worker = BackupQueueWorker()
