"""
core/feed_watcher.py
=======================
Servizio periodico di Custom RSS/Alert (SPEC.md §10.3, §10.7, §10.8)
— stesso pattern architetturale di core/event_log_retention.py e
core/memory_guard.py: una classe con un tasks.loop periodico,
avviata una volta da main.py, non un Cog con comandi.

Un HTTP client asincrono (aiohttp, già una dipendenza di discord.py,
nessuna nuova dipendenza aggiunta) scarica ogni feed sottoscritto,
core/feed_parsing_logic.py fa il resto (analisi XML, cosa è nuovo,
rendering del messaggio) — questo file coordina soltanto.
"""

from __future__ import annotations

import logging

import aiohttp
import discord
from discord.ext import commands, tasks

from core.feed_parsing_logic import find_new_entries, parse_feed, render_alert_message
from core.repositories.feed_subscription_repo import feed_subscription_repo

logger = logging.getLogger("iyokai.feed_watcher")

TICK_SECONDS = 300  # 5 minuti: gli aggiornamenti RSS non sono mai
# davvero istantanei, e un intervallo più corto significherebbe
# scaricare ogni feed più spesso senza un vantaggio reale per
# l'utente finale, solo più traffico verso servizi esterni (Reddit,
# YouTube) che non controlliamo.

REQUEST_TIMEOUT_SECONDS = 15


class FeedWatcherService:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None
        self._http_session: aiohttp.ClientSession | None = None

    async def _fetch_feed_text(self, url: str) -> str | None:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()

        try:
            async with self._http_session.get(
                url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            ) as risposta:
                if risposta.status != 200:
                    logger.warning(
                        "Feed %s ha risposto con status %d, salto questo giro.",
                        url,
                        risposta.status,
                    )
                    return None
                return await risposta.text()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning(
                "Impossibile scaricare il feed %s: %s — salto questo giro, "
                "riprovo al prossimo tick (%ds).",
                url,
                exc,
                TICK_SECONDS,
            )
            return None

    async def tick(self, bot: commands.Bot) -> None:
        sottoscrizioni = await feed_subscription_repo.get_all_subscriptions()

        for sottoscrizione in sottoscrizioni:
            testo_xml = await self._fetch_feed_text(sottoscrizione.feed_url)
            if testo_xml is None:
                continue

            voci = parse_feed(testo_xml)
            if not voci:
                continue

            nuove = find_new_entries(voci, sottoscrizione.last_seen_entry_id)

            # Sempre aggiorniamo last_seen alla voce più recente del
            # feed ORA, sia che ci fossero voci nuove sia no — anche
            # al primo controllo mai fatto (last_seen_entry_id=None),
            # per non ripubblicare l'intero storico al giro
            # successivo.
            await feed_subscription_repo.update_last_seen(
                sottoscrizione.id, voci[0].entry_id
            )

            if not nuove:
                continue

            guild = bot.get_guild(sottoscrizione.guild_id)
            canale = guild.get_channel(sottoscrizione.channel_id) if guild else None
            if not isinstance(canale, discord.TextChannel):
                logger.warning(
                    "Canale %s non raggiungibile per la sottoscrizione #%s (server %s).",
                    sottoscrizione.channel_id,
                    sottoscrizione.id,
                    sottoscrizione.guild_id,
                )
                continue

            # Dal più vecchio al più recente delle nuove voci — così
            # nel canale appaiono in ordine cronologico, non al
            # contrario.
            for voce in reversed(nuove):
                messaggio = render_alert_message(
                    sottoscrizione.message_template,
                    label=sottoscrizione.label,
                    title=voce.title,
                    link=voce.link,
                )
                try:
                    await canale.send(messaggio)
                except discord.HTTPException:
                    logger.warning(
                        "Impossibile pubblicare l'alert nel canale %s (server %s).",
                        sottoscrizione.channel_id,
                        sottoscrizione.guild_id,
                    )

    async def close(self) -> None:
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del feed watcher")

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info("Feed watcher avviato (controllo ogni %ds).", TICK_SECONDS)


# Istanza unica, condivisa da tutto il progetto — coerente con
# core/memory_guard.py, core/scheduler.py, core/event_log_retention.py.
feed_watcher = FeedWatcherService()
