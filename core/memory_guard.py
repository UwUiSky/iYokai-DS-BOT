"""
core/memory_guard.py
=======================
Il servizio vero: legge la RAM reale del processo (psutil), forza un
garbage collection quando serve, avvisa il proprietario in DM (con
cooldown — vedi core/memory_guard_logic.py per il perché), e
disconnette i VoiceClient rimasti agganciati a canali vuoti.

Stesso pattern architetturale di core/scheduler.py: una classe con un
tasks.loop periodico, avviata una volta da main.py dopo che bot e
config sono pronti. Non è un Cog con comandi slash — è un servizio
bot-wide, non legato alla configurazione di un singolo server.
"""

from __future__ import annotations

import asyncio
import gc
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.config import config
from core.memory_guard_logic import (
    format_memory_alert,
    should_disconnect_voice_client,
    should_force_gc,
    should_send_alert,
)

logger = logging.getLogger("iyokai.memory_guard")

TICK_SECONDS = 60


class MemoryGuard:
    def __init__(self) -> None:
        self._last_alert_at: datetime | None = None
        self._loop_task: tasks.Loop | None = None

    def read_rss_bytes(self) -> int:
        """
        Legge la RSS (Resident Set Size, la RAM fisica realmente
        occupata) del processo corrente. Chiamata reale a psutil, non
        un valore simulato — è esattamente il numero che conterebbe
        su Oracle Free Tier.
        """
        import psutil
        return psutil.Process().memory_info().rss

    async def _send_alert(
        self,
        bot: commands.Bot,
        rss_bytes: int,
        pool_size: int | None = None,
        pool_idle: int | None = None,
        task_count: int | None = None,
    ) -> None:
        try:
            owner = await bot.fetch_user(config.OWNER_ID)
            await owner.send(
                format_memory_alert(
                    rss_bytes,
                    config.MEMORY_ALERT_THRESHOLD_MB,
                    pool_size=pool_size,
                    pool_idle=pool_idle,
                    task_count=task_count,
                )
            )
            self._last_alert_at = datetime.now(timezone.utc)
        except discord.HTTPException:
            logger.warning(
                "Impossibile inviare l'alert DM di Memory Guard al "
                "proprietario (DM chiusi o utente irraggiungibile)."
            )

    async def _cleanup_idle_voice_clients(self, bot: commands.Bot) -> None:
        """
        Disconnette qualunque VoiceClient rimasto agganciato a un
        canale ormai senza membri umani. Rete di sicurezza generica:
        il modulo Music (non ancora scritto, vedi SPEC.md §9) avrà
        una propria logica di auto-leave più raffinata con timer di
        grazia; questa gira comunque, per qualunque VoiceClient
        rimasto attaccato per un motivo qualsiasi (es. un crash
        parziale che ha impedito la disconnessione pulita).
        """
        for voice_client in list(bot.voice_clients):
            channel = voice_client.channel
            if channel is None:
                continue
            umani = [m for m in channel.members if not m.bot]
            if should_disconnect_voice_client(len(umani)):
                try:
                    await voice_client.disconnect(force=False)
                    logger.info(
                        "Memory Guard: disconnesso VoiceClient inattivo dal "
                        "canale %s (nessun membro umano presente).",
                        channel.id,
                    )
                except Exception:
                    logger.exception(
                        "Errore disconnettendo un VoiceClient inattivo (canale %s)",
                        channel.id,
                    )

    async def tick(self, bot: commands.Bot) -> None:
        """Un giro completo: leggi, eventualmente pulisci, eventualmente avvisa."""
        rss_before = self.read_rss_bytes()

        # Forziamo il GC da WARNING in su (non solo a CRITICAL come
        # nella versione a soglia singola): intervenire prima che il
        # problema sia già serio, un GC è comunque economico.
        if should_force_gc(rss_before, config.MEMORY_ALERT_THRESHOLD_MB):
            gc.collect()

        rss_after = self.read_rss_bytes()

        # Pool DB e conteggio task: informazioni aggiuntive per
        # l'alert (BACKLOG.md §4 — versione ridotta del Memory Guard
        # a soglie scalate, limitata alle metriche già misurabili
        # senza nuove dipendenze). Presi in modo tollerante: se il
        # DB non è ancora connesso (bot appena avviato) o qualcosa
        # va storto, l'alert parte comunque senza quei dettagli
        # invece di far fallire l'intero tick.
        pool_size = pool_idle = None
        try:
            from core.database import db
            pool = db.pool
            pool_size = pool.get_size()
            pool_idle = pool.get_idle_size()
        except Exception:
            pass
        task_count = len(asyncio.all_tasks())

        if should_send_alert(
            rss_after, config.MEMORY_ALERT_THRESHOLD_MB, self._last_alert_at
        ):
            await self._send_alert(bot, rss_after, pool_size, pool_idle, task_count)

        await self._cleanup_idle_voice_clients(bot)

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del Memory Guard")

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info(
            "Memory Guard avviato (controllo ogni %ds, soglia %dMB).",
            TICK_SECONDS,
            config.MEMORY_ALERT_THRESHOLD_MB,
        )


# Istanza unica, condivisa da tutto il progetto — coerente con
# core/scheduler.py e core/database.py.
memory_guard = MemoryGuard()
