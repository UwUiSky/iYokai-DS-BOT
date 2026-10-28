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

import asyncio
import logging
from dataclasses import replace

import discord
from discord.ext import commands, tasks

from core.alert_options_logic import invia_alert
from core.bot_ready import attendi_bot_pronto
from core.feed_alert_gate import AvvisoUnaVolta, filtra_attive
from core.feed_parsing_logic import (
    data_piu_recente,
    find_new_entries,
    parse_feed,
    render_alert_message,
)
from core.repositories.alert_options_repo import alert_options_repo
from core.repositories.feed_subscription_repo import feed_subscription_repo
from core.safe_http import Scaricamento, chiudi_sessione_condivisa, safe_get_con_etag

logger = logging.getLogger("iyokai.feed_watcher")

TICK_SECONDS = 300  # 5 minuti: gli aggiornamenti RSS non sono mai
# davvero istantanei, e un intervallo più corto significherebbe
# scaricare ogni feed più spesso senza un vantaggio reale per
# l'utente finale, solo più traffico verso servizi esterni (Reddit,
# YouTube) che non controlliamo.


# Quanti feed diversi si scaricano insieme (M 11.9, PERF-7).
SCARICHI_IN_PARALLELO = 5


class FeedWatcherService:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None
        self._avvisi = AvvisoUnaVolta()
        self._etag_per_url: dict[str, str] = {}

    async def _fetch_feed_text(self, url: str, etag: str | None = None) -> Scaricamento | None:
        # SEC-8: url è scelto liberamente dall'admin del server
        # (/alerts add) — safe_get rifiuta indirizzi interni,
        # loopback, metadati cloud, ecc. e logga da sé il motivo del
        # rifiuto o dell'errore. Sessione condivisa, User-Agent ed ETag
        # (304 = feed invariato) sono in safe_get_con_etag.
        return await safe_get_con_etag(url, etag)

    async def tick(self, bot: commands.Bot) -> None:
        sottoscrizioni = await feed_subscription_repo.get_all_subscriptions()
        # LC-7: server con il modulo spento = nessuno scarico, nessun messaggio.
        sottoscrizioni = await filtra_attive(sottoscrizioni)

        # M 11.9: indirizzi uguali (anche di server diversi) = uno scarico.
        per_url: dict[str, list] = {}
        for sottoscrizione in sottoscrizioni:
            per_url.setdefault(sottoscrizione.feed_url, []).append(sottoscrizione)
        self._etag_per_url = {u: e for u, e in self._etag_per_url.items() if u in per_url}

        semaforo = asyncio.Semaphore(SCARICHI_IN_PARALLELO)

        async def scarica(url: str, gruppo: list):
            # Una sottoscrizione mai inizializzata (last_seen vuoto) ha
            # bisogno del contenuto: niente ETag, altrimenti un 304 la
            # lascerebbe senza stato.
            serve_tutto = any(s.last_seen_entry_id is None for s in gruppo)
            etag = None if serve_tutto else self._etag_per_url.get(url)
            async with semaforo:
                return await self._fetch_feed_text(url, etag)

        esiti = await asyncio.gather(
            *(scarica(url, gruppo) for url, gruppo in per_url.items()),
            return_exceptions=True,
        )

        for (url, gruppo), esito in zip(per_url.items(), esiti):
            if isinstance(esito, BaseException):
                logger.error("Errore nello scarico del feed %s: %r", url, esito)
                continue
            if esito is None or esito.non_modificato or esito.testo is None:
                continue
            # P4: l'ETag si ricorda solo se TUTTE le sottoscrizioni del
            # gruppo sono state elaborate: se una solleva (DB, ...), al
            # giro dopo il feed va riscaricato, non risposto con 304.
            self._etag_per_url.pop(url, None)
            tutte_ok = True

            voci = parse_feed(esito.testo)
            for sottoscrizione in gruppo:
                # BUG-20: ogni sottoscrizione è isolata — un errore su una
                # (feed rotto, dato inatteso) non deve saltare tutte le
                # successive, che appartengono anche ad altri server.
                try:
                    if not await self._controlla_sottoscrizione(bot, sottoscrizione, voci):
                        tutte_ok = False  # c'e' qualcosa da ritentare: niente 304
                except Exception:
                    tutte_ok = False
                    logger.exception(
                        "Errore sulla sottoscrizione #%s (server %s): salto alla prossima.",
                        sottoscrizione.id,
                        sottoscrizione.guild_id,
                    )
            if tutte_ok and esito.etag:
                self._etag_per_url[url] = esito.etag

    async def _controlla_sottoscrizione(self, bot: commands.Bot, sottoscrizione, voci) -> bool:
        """True se non resta nulla da ritentare (invii riusciti o niente da inviare)."""
        if not voci:
            return True

        nuove = find_new_entries(
            voci, sottoscrizione.last_seen_entry_id, sottoscrizione.last_seen_published
        )

        data_feed = data_piu_recente(voci)
        if not nuove:
            # Primo controllo mai fatto: si ricorda lo stato attuale senza
            # pubblicare lo storico. Riga vecchia senza data: si completa.
            # Altrimenti niente da scrivere: in particolare mai tornare
            # indietro con una copia vecchia del feed (CDN, mirror).
            if sottoscrizione.last_seen_entry_id is None:
                await feed_subscription_repo.update_last_seen(
                    sottoscrizione.id, voci[0].entry_id, data_feed
                )
            elif sottoscrizione.last_seen_published is None and data_feed is not None:
                await feed_subscription_repo.update_last_seen(
                    sottoscrizione.id, sottoscrizione.last_seen_entry_id, data_feed
                )
            return True

        guild = bot.get_guild(sottoscrizione.guild_id)
        canale = guild.get_channel(sottoscrizione.channel_id) if guild else None
        if not isinstance(canale, discord.TextChannel):
            if self._avvisi.prima_volta(("rss", sottoscrizione.id)):
                logger.warning(
                    "Canale %s non raggiungibile per la sottoscrizione #%s (server %s).",
                    sottoscrizione.channel_id,
                    sottoscrizione.id,
                    sottoscrizione.guild_id,
                )
            return False
        self._avvisi.riarma(("rss", sottoscrizione.id))

        opz = replace(await alert_options_repo.get("RSS", sottoscrizione.id), watch_button=False)

        # Dal più vecchio al più recente delle nuove voci — così
        # nel canale appaiono in ordine cronologico, non al
        # contrario.
        for voce in reversed(nuove):
            if opz.paused:
                # ALR-036: in pausa non si pubblica, ma si va avanti: alla ripresa niente raffica.
                await feed_subscription_repo.update_last_seen(
                    sottoscrizione.id, voce.entry_id, voce.published
                )
                continue
            messaggio = render_alert_message(
                sottoscrizione.message_template,
                label=sottoscrizione.label,
                title=voce.title,
                link=voce.link,
            )
            try:
                await invia_alert(canale, messaggio, opz)
            except discord.HTTPException:
                # P3: invio fallito = niente avanzamento; la voce (e le
                # successive, per mantenere l'ordine) si ritenta al giro dopo.
                logger.warning(
                    "Impossibile pubblicare l'alert nel canale %s (server %s).",
                    sottoscrizione.channel_id,
                    sottoscrizione.guild_id,
                )
                return False
            # P3: si avanza solo dopo un invio riuscito, voce per voce;
            # la data non torna mai indietro (GREATEST nel repository).
            await feed_subscription_repo.update_last_seen(
                sottoscrizione.id, voce.entry_id, voce.published
            )
        return True

    async def close(self) -> None:
        # La sessione HTTP e' quella condivisa di core/safe_http.py.
        await chiudi_sessione_condivisa()

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
