"""
core/backup_queue_worker.py
===========================
Coda dei job di backup (SPEC.md §11.2): un loop periodico avviato da main.py.
Un job alla volta. Il job nasce dal collegamento con il codice (D8) già legato
al server di backup creato da un admin; il Creator lo porta allo stato
corrente con il suo client e il proprietario del server principale riceve
un riepilogo. Il giro parte solo quando il bot principale è pronto.
Funzioni coperte: SPEC §11.2, M 12.1, M 12.2, REVIEW.md BUG-19
"""

from __future__ import annotations

import logging
import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.backup_orchestrator import popola_server_backup, riassunto_copia
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
        riepilogo finale) — un solo punto
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

    async def _notifica_amministratore(
        self, main_guild: discord.Guild, backup_guild: discord.Guild, riepilogo: str
    ) -> None:
        """DM al proprietario: la copia è finita. Se il DM fallisce il job resta completato."""
        testo = f"La copia di **{main_guild.name}** in **{backup_guild.name}** è finita. Da ora il Creator la tiene aggiornata."
        if riepilogo:
            testo += f"\n\n{riepilogo}"
        embed = discord.Embed(
            title="📦 Backup pronto", description=testo[:4000], color=discord.Color.blurple()
        )
        await self._manda_dm(main_guild, embed, contesto="il backup pronto")

    async def _scadenza_job(self) -> None:
        """Un job bloccato da oltre 24 ore non deve fermare la coda."""
        scaduti = await backup_repo.expire_stale_jobs()
        if scaduti:
            logger.info("%d job di backup scaduti (oltre 24h bloccati).", scaduti)

    async def tick(
        self,
        creator_client: discord.Client,
        main_bot: commands.Bot,
        main_permissions: discord.Permissions | None = None,
    ) -> None:
        """Un giro. ``main_permissions`` resta nella firma per ``main.py``, non serve più."""
        await self._scadenza_job()

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

        if job.backup_guild_id is None:
            await backup_repo.mark_failed(
                job.id, "Job senza server di backup: rilancia il collegamento con il codice."
            )
            return

        # M 12.2: la copia usa il client del Creator, non quello principale.
        backup_guild = creator_client.get_guild(job.backup_guild_id)
        if backup_guild is None:
            await backup_repo.mark_failed(
                job.id, "iYokai Creator non è nel server di backup: invitalo e rilancia il collegamento."
            )
            return

        try:
            mappa_webhook_mirror, riepilogo = await popola_server_backup(main_guild, backup_guild)
        except Exception as exc:
            logger.exception("Job di backup #%s fallito durante la copia.", job.id)
            await backup_repo.mark_failed(job.id, str(exc)[:500])
            return

        try:
            # Mirror in tempo reale (SPEC.md §11.9): sostituisce la mappa precedente.
            await backup_mirror_repo.save_mapping(
                main_guild_id=job.main_guild_id,
                backup_guild_id=backup_guild.id,
                channel_webhook_map=mappa_webhook_mirror,
            )
            await backup_repo.mark_completed(job.id, backup_guild_id=backup_guild.id)
        except Exception as exc:
            logger.exception("Job di backup #%s fallito dopo la copia.", job.id)
            await backup_repo.mark_failed(job.id, str(exc)[:500])
            return
        await self._notifica_amministratore(main_guild, backup_guild, riassunto_copia(riepilogo))

    async def _giro(
        self,
        creator_client: discord.Client,
        main_bot: commands.Bot,
        main_permissions: discord.Permissions | None,
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
            await attendi_bot_pronto(main_bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Backup queue worker avviato (controllo ogni %ds).", TICK_SECONDS)


backup_queue_worker = BackupQueueWorker()
