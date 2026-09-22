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
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.backup_orchestrator import start_backup_job
from core.backup_reminder_logic import (
    MAX_CREATOR_GUILDS,
    format_slot_wait_message,
    format_time_remaining,
    should_send_timeout_reminder,
)
from core.repositories.backup_repo import backup_repo

logger = logging.getLogger("iyokai.backup_queue_worker")

TICK_SECONDS = 60


class BackupQueueWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def _trova_proprietario(self, guild: discord.Guild) -> discord.abc.Snowflake | None:
        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_member(guild.owner_id)
            except discord.HTTPException:
                owner = None
        return owner

    async def _manda_dm(self, guild: discord.Guild, embed: discord.Embed, contesto: str) -> None:
        """
        Condiviso da tutti i tipi di notifica (backup pronto,
        promemoria di scadenza, avviso slot pieni) — un solo punto
        che trova il proprietario e manda il DM, non tre copie della
        stessa logica.
        """
        owner = await self._trova_proprietario(guild)
        if owner is None:
            logger.warning(
                "Impossibile trovare il proprietario del server %s per %s.", guild.id, contesto
            )
            return

        try:
            await owner.send(embed=embed)
        except discord.HTTPException:
            logger.warning(
                "Impossibile mandare il DM di %s al proprietario del server %s.",
                contesto,
                guild.id,
            )

    async def _notifica_amministratore(self, main_guild: discord.Guild, url_invito: str) -> None:
        """
        Un link che crea/trasferisce un intero server merita un
        messaggio privato, non un post in un canale qualsiasi. Se il
        DM fallisce il job resta comunque 'completed' con il server
        creato e clonato, solo senza che nessuno abbia ancora
        ricevuto l'invito per completare il trasferimento.
        """
        embed = discord.Embed(
            title="📦 Backup pronto",
            description=(
                f"Il backup di **{main_guild.name}** è stato creato e popolato. "
                f"Clicca il link qui sotto per completare l'operazione (iYokai Main "
                f"deve entrare nel nuovo server prima che diventi utilizzabile):\n\n{url_invito}"
            ),
            color=discord.Color.blurple(),
        )
        await self._manda_dm(main_guild, embed, contesto="il backup pronto")

    async def _controlla_promemoria_scadenza(self, main_bot: commands.Bot) -> None:
        """
        Richiesta esplicita dell'utente: un conto alla rovescia
        prima che un job in attesa del click umano venga annullato
        (timeout 24h). Un solo promemoria per job (should_send_
        timeout_reminder si occupa di non ripeterlo ad ogni tick).
        """
        adesso = datetime.now(timezone.utc)
        for job in await backup_repo.get_running_jobs():
            if not should_send_timeout_reminder(
                job.created_at, adesso, reminder_already_sent=job.reminder_sent_at is not None
            ):
                continue

            main_guild = main_bot.get_guild(job.main_guild_id)
            if main_guild is None:
                continue

            tempo_rimanente = format_time_remaining(job.created_at, adesso)
            embed = discord.Embed(
                title="⏳ Promemoria: backup in scadenza",
                description=(
                    f"Il backup di **{main_guild.name}** è pronto ma è ancora in attesa "
                    f"che tu clicchi il link di invito — se non lo fai entro **{tempo_rimanente}**, "
                    f"l'operazione verrà annullata automaticamente."
                ),
                color=discord.Color.orange(),
            )
            await self._manda_dm(main_guild, embed, contesto="il promemoria di scadenza")
            await backup_repo.mark_reminder_sent(job.id)

    async def tick(
        self,
        creator_client: discord.Client,
        main_bot: commands.Bot,
        main_permissions: discord.Permissions,
    ) -> None:
        scaduti = await backup_repo.expire_stale_jobs()
        if scaduti:
            logger.info("%d job di backup scaduti (oltre 24h bloccati).", scaduti)

        await self._controlla_promemoria_scadenza(main_bot)

        job = await backup_repo.get_next_pending_job()
        if job is None:
            return

        # Creator resta SEMPRE sotto il limite di 10 server (SPEC.md
        # §11.1) — se è già al massimo (un'altra clonazione ancora in
        # attesa del click di qualcun altro), non proviamo a
        # crearne un altro ora: aspettiamo il prossimo tick, quando
        # magari uno slot si sarà liberato.
        occupati = len(creator_client.guilds)
        if occupati >= MAX_CREATOR_GUILDS:
            main_guild = main_bot.get_guild(job.main_guild_id)
            if main_guild is not None and job.reminder_sent_at is None:
                embed = discord.Embed(
                    title="⏸️ Backup in coda",
                    description=format_slot_wait_message(occupati),
                    color=discord.Color.orange(),
                )
                await self._manda_dm(main_guild, embed, contesto="l'avviso di slot pieni")
                await backup_repo.mark_reminder_sent(job.id)
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
