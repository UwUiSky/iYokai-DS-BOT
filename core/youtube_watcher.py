"""
core/youtube_watcher.py
===========================
Servizio periodico di YouTube live (SPEC.md §10.4) — stesso pattern
architetturale di core/twitch_watcher.py. A differenza di Twitch (un
solo access token condiviso per tutte le richieste), la YouTube Data
API usa una API key semplice passata come parametro di query, niente
OAuth da rinnovare.

Intervallo più lungo di Twitch (TICK_SECONDS) apposta: ogni tick
consuma 100 unità di quota PER CANALE sottoscritto (search.list),
su una quota giornaliera gratuita di 10.000 — con TICK_SECONDS=300 e
un solo canale sottoscritto si consumano circa 28.800 unità/giorno,
già sopra il limite gratuito; questo è esplicitamente il motivo per
cui SPEC.md segnava questa voce come "quota a consumo" e per cui
resta disattivata di default (YOUTUBE_API_KEY vuota). Chi la abilita
deve monitorare la propria quota sulla Google Cloud Console e
sottoscrivere pochi canali, o richiedere un aumento di quota — non è
un limite che questo codice possa risolvere da solo.
"""

# DA FARE (issue #67, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §11 (Feed e alert).

from __future__ import annotations

import logging

import aiohttp
import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.config import config
from core.youtube_api_logic import parse_search_live_response
from core.repositories.youtube_subscription_repo import youtube_subscription_repo

logger = logging.getLogger("iyokai.youtube_watcher")

TICK_SECONDS = 300  # vedi il docstring del modulo: quota a consumo,
# più lento apposta di Twitch (90s).

REQUEST_TIMEOUT_SECONDS = 15
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class YoutubeWatcherService:
    def __init__(self, search_url: str = YOUTUBE_SEARCH_URL) -> None:
        self._loop_task: tasks.Loop | None = None
        self._http_session: aiohttp.ClientSession | None = None
        self._search_url = search_url

    def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def _fetch_live_status(self, youtube_channel_id: str) -> dict | None:
        if not config.YOUTUBE_API_KEY:
            return None

        sessione = self._get_session()
        try:
            async with sessione.get(
                self._search_url,
                params={
                    "key": config.YOUTUBE_API_KEY,
                    "channelId": youtube_channel_id,
                    "eventType": "live",
                    "type": "video",
                    "part": "snippet",
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as risposta:
                if risposta.status != 200:
                    logger.warning(
                        "Richiesta a YouTube search.list fallita con status %d "
                        "per il canale %s, salto questo giro.",
                        risposta.status,
                        youtube_channel_id,
                    )
                    return None
                return await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning(
                "Impossibile contattare la YouTube Data API per il canale %s: %s — "
                "salto questo giro, riprovo al prossimo tick (%ds).",
                youtube_channel_id,
                exc,
                TICK_SECONDS,
            )
            return None

    async def tick(self, bot: commands.Bot) -> None:
        if not config.YOUTUBE_API_KEY:
            return

        sottoscrizioni = await youtube_subscription_repo.get_all_subscriptions()
        if not sottoscrizioni:
            return

        for sottoscrizione in sottoscrizioni:
            # Una chiamata per canale (a differenza di Twitch, search.list
            # non supporta un batch di più canali in una sola richiesta).
            payload = await self._fetch_live_status(sottoscrizione.youtube_channel_id)
            if payload is None:
                continue

            stato = parse_search_live_response(payload, sottoscrizione.youtube_channel_id)

            appena_andato_live = stato.is_live and not sottoscrizione.last_known_live
            appena_andato_offline = not stato.is_live and sottoscrizione.last_known_live

            if not (appena_andato_live or appena_andato_offline):
                continue

            await youtube_subscription_repo.update_last_known_live(
                sottoscrizione.id, stato.is_live
            )

            guild = bot.get_guild(sottoscrizione.guild_id)
            canale = guild.get_channel(sottoscrizione.channel_id) if guild else None
            if not isinstance(canale, discord.TextChannel):
                logger.warning(
                    "Canale %s non raggiungibile per la sottoscrizione YouTube #%s (server %s).",
                    sottoscrizione.channel_id,
                    sottoscrizione.id,
                    sottoscrizione.guild_id,
                )
                continue

            if appena_andato_live:
                messaggio = sottoscrizione.live_message_template.format(
                    label=sottoscrizione.label,
                    title=stato.title or "",
                    video_id=stato.video_id or "",
                )
            else:
                messaggio = sottoscrizione.offline_message_template.format(
                    label=sottoscrizione.label
                )

            try:
                await canale.send(messaggio)
            except discord.HTTPException:
                logger.warning(
                    "Impossibile pubblicare l'alert YouTube nel canale %s (server %s).",
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
