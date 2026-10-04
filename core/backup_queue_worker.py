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
orchestrator.py). Il loop aspetta solo il bot principale: se il
Creator non è pronto il giro viene saltato.
Funzioni coperte: SPEC §11.2, REVIEW.md BUG-19.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.backup_orchestrator import elimina_server_creato, start_backup_job
from core.backup_reminder_logic import (
    MAX_CREATOR_GUILDS,
    format_slot_wait_message,
    format_time_remaining,
    should_send_timeout_reminder,
)
from core.repositories.backup_mirror_repo import backup_mirror_repo
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

    async def _libera_server_scaduti(self, creator_client: discord.Client) -> None:
        """
        BUG-4: un job scaduto lascia un server creato dal Creator che
        occupa uno slot (max 10). Prima di segnarli scaduti, il
        Creator cancella i server di quei job.
        """
        stale = await backup_repo.list_stale_jobs()
        scaduti = await backup_repo.expire_stale_jobs()
        for job in stale:
            if job.backup_guild_id is not None:
                await elimina_server_creato(creator_client, job.backup_guild_id)
        if scaduti:
            logger.info("%d job di backup scaduti (oltre 24h bloccati).", scaduti)

    async def tick(
        self,
        creator_client: discord.Client,
        main_bot: commands.Bot,
        main_permissions: discord.Permissions,
    ) -> None:
        await self._libera_server_scaduti(creator_client)

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
            nuovo_server, url_invito, mappa_webhook_mirror = await start_backup_job(
                creator_client, main_guild, main_bot.user.id, main_permissions
            )
        except Exception as exc:
            logger.exception("Job di backup #%s fallito durante la creazione/clonazione.", job.id)
            await backup_repo.mark_failed(job.id, str(exc))
            return

        try:
            await backup_repo.set_backup_guild_id(job.id, nuovo_server.id)
            # Mirror in tempo reale (SPEC.md §11.9): sostituisce la mappa
            # precedente per questo main (il vecchio backup, se esisteva,
            # non è più valido) con quella appena creata.
            await backup_mirror_repo.save_mapping(
                main_guild_id=job.main_guild_id,
                backup_guild_id=nuovo_server.id,
                channel_webhook_map=mappa_webhook_mirror,
            )
        except Exception as exc:
            logger.exception("Job di backup #%s fallito dopo la creazione del server.", job.id)
            await elimina_server_creato(creator_client, nuovo_server.id)
            await backup_repo.mark_failed(job.id, str(exc))
            return
        await self._notifica_amministratore(main_guild, url_invito)

    async def _giro(
        self,
        creator_client: discord.Client,
        main_bot: commands.Bot,
        main_permissions: discord.Permissions,
    ) -> None:
        """Un giro del loop: salta se il Creator non è pronto, non solleva mai."""
        if not creator_client.is_ready():
            # Il Creator può non essere partito (token sbagliato): è
            # tollerato, si riprova al giro dopo.
            logger.debug("Il Creator non è pronto: giro della coda dei backup saltato.")
            return
        try:
            await self.tick(creator_client, main_bot, main_permissions)
        except Exception:
            logger.exception("Errore nel tick del backup queue worker")

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
            await self._giro(creator_client, main_bot, main_permissions)

        @_loop.before_loop
        async def _before():
            # Solo il bot principale: il Creator si controlla a ogni giro.
            # La pulizia dei server orfani (pulisci_server_orfani) non
            # viene richiamata finché BUG-26 è aperto: cancellerebbe
            # anche server validi che questo database non conosce.
            await attendi_bot_pronto(main_bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Backup queue worker avviato (controllo ogni %ds).", TICK_SECONDS)


backup_queue_worker = BackupQueueWorker()
