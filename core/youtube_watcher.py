"""
core/youtube_watcher.py
===========================
Servizio periodico di YouTube live (SPEC.md §10.4, D5, M 11.1) —
stesso pattern architetturale di core/twitch_watcher.py.

Quota: `search.list` costa 100 unita' a chiamata (BUG-16, LIM-45) e
finiva i 10.000 gratuiti in poche ore. Ora, per ogni giro:
  1. feed RSS del canale (nessuna quota, via core/safe_http.py), uno
     solo anche se piu' server seguono lo stesso canale;
  2. gli ID dei video piu' recenti di tutti i canali, senza doppioni,
     vanno in UNA `videos.list` (1 unita') per gruppo di 50 ID;
  3. `liveBroadcastContent == "live"` dice se il canale e' in diretta.
Con 10 canali: una chiamata a giro, 1 unita' invece di 1.000.
"""

from __future__ import annotations

import logging

import aiohttp
import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.config import config
from core.feed_alert_gate import AvvisoUnaVolta, filtra_attive
from core.feed_parsing_logic import parse_feed
from core.repositories.youtube_subscription_repo import youtube_subscription_repo
from core.safe_http import chiudi_sessione_condivisa, safe_get
from core.alert_options_logic import AlertOptions
from core.live_alert_flow import carica_contesto, pubblica_cambio_live
from core.template_renderer import render_template
from core.youtube_api_logic import (
    VIDEO_PER_CANALE,
    VIDEOS_LIST_MAX_ID,
    parse_videos_list_response,
    stato_live_del_canale,
    video_id_da_voce,
)

logger = logging.getLogger("iyokai.youtube_watcher")

TICK_SECONDS = 300

REQUEST_TIMEOUT_SECONDS = 15
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


class YoutubeWatcherService:
    def __init__(
        self,
        videos_url: str = YOUTUBE_VIDEOS_URL,
        rss_url_template: str = YOUTUBE_RSS_URL,
    ) -> None:
        self._loop_task: tasks.Loop | None = None
        self._avvisi = AvvisoUnaVolta()
        self._http_session: aiohttp.ClientSession | None = None
        self._videos_url = videos_url
        self._rss_url_template = rss_url_template

    def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def _video_recenti(self, youtube_channel_id: str) -> list[str] | None:
        """ID dei video piu' recenti dal feed RSS del canale; None se il feed non si legge."""
        testo = await safe_get(self._rss_url_template.format(channel_id=youtube_channel_id))
        if testo is None:
            return None
        voci = parse_feed(testo)[:VIDEO_PER_CANALE]
        if not voci:
            return None  # feed vuoto o rotto: meglio non cambiare stato
        ids = [video_id_da_voce(v.entry_id, v.link) for v in voci]
        return [i for i in ids if i]

    async def _fetch_videos(self, video_ids: list[str]) -> dict | None:
        """UNA chiamata videos.list per un gruppo di al massimo 50 ID."""
        sessione = self._get_session()
        try:
            async with sessione.get(
                self._videos_url,
                params={
                    "key": config.YOUTUBE_API_KEY,
                    "id": ",".join(video_ids),
                    "part": "snippet",
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as risposta:
                if risposta.status != 200:
                    logger.warning(
                        "Richiesta a YouTube videos.list fallita con status %d, "
                        "salto questo giro.",
                        risposta.status,
                    )
                    return None
                return await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning(
                "Impossibile contattare la YouTube Data API: %s — riprovo al prossimo tick (%ds).",
                exc,
                TICK_SECONDS,
            )
            return None

    async def tick(self, bot: commands.Bot) -> None:
        if not config.YOUTUBE_API_KEY:
            return

        sottoscrizioni = await youtube_subscription_repo.get_all_subscriptions()
        # LC-7: server con il modulo spento = nessuna richiesta, nessuna quota.
        sottoscrizioni = await filtra_attive(sottoscrizioni)
        if not sottoscrizioni:
            return

        # 1) feed RSS: un solo scarico per canale, anche se seguito da piu' server.
        video_per_canale: dict[str, list[str]] = {}
        for channel_id in dict.fromkeys(s.youtube_channel_id for s in sottoscrizioni):
            ids = await self._video_recenti(channel_id)
            if ids is not None:
                video_per_canale[channel_id] = ids

        # 2) videos.list: ID unici, a gruppi di 50.
        tutti = list(dict.fromkeys(i for ids in video_per_canale.values() for i in ids))
        info = {}
        gruppi_riusciti = set()
        for n in range(0, len(tutti), VIDEOS_LIST_MAX_ID):
            gruppo = tutti[n : n + VIDEOS_LIST_MAX_ID]
            payload = await self._fetch_videos(gruppo)
            if payload is None:
                continue
            info.update(parse_videos_list_response(payload))
            gruppi_riusciti.update(gruppo)

        stati = {}
        for channel_id, ids in video_per_canale.items():
            if all(i in gruppi_riusciti for i in ids):  # risposta completa per questo canale
                stati[channel_id] = stato_live_del_canale(channel_id, ids, info)

        opzioni, ruoli = await carica_contesto("YT", sottoscrizioni)
        for sottoscrizione in sottoscrizioni:
            stato = stati.get(sottoscrizione.youtube_channel_id)
            if stato is None:
                continue

            appena_andato_live = stato.is_live and not sottoscrizione.last_known_live
            appena_andato_offline = not stato.is_live and sottoscrizione.last_known_live

            if not (appena_andato_live or appena_andato_offline):
                continue

            if appena_andato_live:
                messaggio = render_template(
                    sottoscrizione.live_message_template,
                    {
                        "label": sottoscrizione.label,
                        "title": stato.title or "",
                        "video_id": stato.video_id or "",
                    },
                )
            else:
                messaggio = render_template(
                    sottoscrizione.offline_message_template,
                    {"label": sottoscrizione.label},
                )

            await pubblica_cambio_live(
                bot, sottoscrizione, "YT",
                in_diretta=stato.is_live, testo=messaggio,
                url=f"https://www.youtube.com/watch?v={stato.video_id}" if stato.video_id else None,
                opz=opzioni.get(sottoscrizione.id, AlertOptions()),
                ruolo_live_id=ruoli.get(sottoscrizione.guild_id),
                repo_stato=youtube_subscription_repo,
                avvisi=self._avvisi, nome="YouTube",
            )

    async def close(self) -> None:
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None
        await chiudi_sessione_condivisa()

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        if not config.YOUTUBE_API_KEY:
            logger.info(
                "YOUTUBE_API_KEY non configurata — il watcher YouTube live "
                "resta inattivo finché non viene impostata."
            )
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del YouTube watcher")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("YouTube watcher avviato (controllo ogni %ds).", TICK_SECONDS)


youtube_watcher = YoutubeWatcherService()
