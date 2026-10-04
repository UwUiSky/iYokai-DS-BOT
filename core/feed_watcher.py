"""
core/feed_watcher.py
=======================
Servizio periodico di Custom RSS/Alert (SPEC.md §10.3, §10.7, §10.8)
— stesso pattern architetturale di core/event_log_retention.py e
core/memory_guard.py: una classe con un tasks.loop periodico,
avviata una volta da main.py, non un Cog con comandi.

Lo scaricamento vero passa da core/safe_http.py (SEC-8): l'URL è
scelto liberamente dall'admin del server, quindi va protetto da SSRF
prima di essere raggiunto. core/feed_parsing_logic.py fa il resto
(analisi XML, cosa è nuovo, rendering del messaggio) — questo file
coordina soltanto.
Dipende da: core/safe_http.py (SEC-8)
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.feed_parsing_logic import find_new_entries, parse_feed, render_alert_message
from core.repositories.feed_subscription_repo import feed_subscription_repo
from core.safe_http import safe_get

logger = logging.getLogger("iyokai.feed_watcher")

TICK_SECONDS = 300  # 5 minuti: gli aggiornamenti RSS non sono mai
# davvero istantanei, e un intervallo più corto significherebbe
# scaricare ogni feed più spesso senza un vantaggio reale per
# l'utente finale, solo più traffico verso servizi esterni (Reddit,
# YouTube) che non controlliamo.


class FeedWatcherService:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def _fetch_feed_text(self, url: str) -> str | None:
        # SEC-8: url è scelto liberamente dall'admin del server
        # (/alerts add) — safe_get rifiuta indirizzi interni,
        # loopback, metadati cloud, ecc. e logga da sé il motivo del
        # rifiuto o dell'errore.
        return await safe_get(url)

    async def tick(self, bot: commands.Bot) -> None:
        sottoscrizioni = await feed_subscription_repo.get_all_subscriptions()

        for sottoscrizione in sottoscrizioni:
            # BUG-20: ogni sottoscrizione è isolata — un errore su una
            # (feed rotto, dato inatteso) non deve saltare tutte le
            # successive, che appartengono anche ad altri server.
            try:
                await self._controlla_sottoscrizione(bot, sottoscrizione)
            except Exception:
                logger.exception(
                    "Errore sulla sottoscrizione #%s (server %s): salto alla prossima.",
                    sottoscrizione.id,
                    sottoscrizione.guild_id,
                )

    async def _controlla_sottoscrizione(self, bot: commands.Bot, sottoscrizione) -> None:
        testo_xml = await self._fetch_feed_text(sottoscrizione.feed_url)
        if testo_xml is None:
            return

        voci = parse_feed(testo_xml)
        if not voci:
            return

        nuove = find_new_entries(voci, sottoscrizione.last_seen_entry_id)

        # Sempre aggiorniamo last_seen alla voce più recente del
        # feed ORA, sia che ci fossero voci nuove sia no — anche
        # al primo controllo mai fatto (last_seen_entry_id=None),
        # per non ripubblicare l'intero storico al giro
        # successivo.
        await feed_subscription_repo.update_last_seen(sottoscrizione.id, voci[0].entry_id)

        if not nuove:
            return

        guild = bot.get_guild(sottoscrizione.guild_id)
        canale = guild.get_channel(sottoscrizione.channel_id) if guild else None
        if not isinstance(canale, discord.TextChannel):
            logger.warning(
                "Canale %s non raggiungibile per la sottoscrizione #%s (server %s).",
                sottoscrizione.channel_id,
                sottoscrizione.id,
                sottoscrizione.guild_id,
            )
            return

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
        # SEC-8: safe_get apre e chiude la propria ClientSession ad
        # ogni chiamata (nessuna sessione persistente qui da
        # chiudere) — il metodo resta per compatibilità con chi lo
        # chiama già (main.py, i test).
        return

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
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Feed watcher avviato (controllo ogni %ds).", TICK_SECONDS)


# Istanza unica, condivisa da tutto il progetto — coerente con
# core/memory_guard.py, core/scheduler.py, core/event_log_retention.py.
feed_watcher = FeedWatcherService()
