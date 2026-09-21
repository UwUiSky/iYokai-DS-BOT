"""
core/twitch_watcher.py
=========================
Servizio periodico di Twitch live/offline (SPEC.md §10.1, §10.2) —
stesso pattern architetturale di core/feed_watcher.py. Gestisce da
solo il token OAuth (Client Credentials Flow): lo richiede alla
prima chiamata e lo rinnova prima che scada, senza che il chiamante
se ne debba preoccupare.

URL di base passabili al costruttore (non hardcoded nel corpo dei
metodi) proprio per poter puntare un test a un server locale finto
invece che alla vera api.twitch.tv — stesso principio già usato per
core/feed_watcher.py (lì con aiohttp.test_utils.TestServer).
"""

from __future__ import annotations

import logging
import time

import aiohttp
import discord
from discord.ext import commands, tasks

from core.config import config
from core.twitch_api_logic import parse_app_access_token_response, parse_get_streams_response
from core.repositories.twitch_subscription_repo import twitch_subscription_repo

logger = logging.getLogger("iyokai.twitch_watcher")

TICK_SECONDS = 90  # più frequente del feed watcher (300s): "live ora"
# ha più valore se notificato in fretta, rispetto a un nuovo video
# che può aspettare qualche minuto in più.

REQUEST_TIMEOUT_SECONDS = 15
TWITCH_OAUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_STREAMS_URL = "https://api.twitch.tv/helix/streams"
# Margine di sicurezza prima della scadenza reale del token, per non
# rischiare di usarne uno scaduto proprio mentre sta per spirare.
TOKEN_REFRESH_MARGIN_SECONDS = 60


class TwitchWatcherService:
    def __init__(
        self,
        oauth_url: str = TWITCH_OAUTH_URL,
        streams_url: str = TWITCH_STREAMS_URL,
    ) -> None:
        self._loop_task: tasks.Loop | None = None
        self._http_session: aiohttp.ClientSession | None = None
        self._oauth_url = oauth_url
        self._streams_url = streams_url
        self._access_token: str | None = None
        self._token_expires_at: float | None = None  # time.monotonic()

    def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def _ensure_access_token(self) -> str | None:
        """
        Restituisce un token valido, richiedendone uno nuovo se non
        ne abbiamo ancora uno o se sta per scadere. None se le
        credenziali non sono configurate o la richiesta fallisce —
        il chiamante salta il tick in quel caso, non solleva.
        """
        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            return None

        if (
            self._access_token is not None
            and self._token_expires_at is not None
            and time.monotonic() < self._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS
        ):
            return self._access_token

        sessione = self._get_session()
        try:
            async with sessione.post(
                self._oauth_url,
                data={
                    "client_id": config.TWITCH_CLIENT_ID,
                    "client_secret": config.TWITCH_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as risposta:
                if risposta.status != 200:
                    logger.warning(
                        "Richiesta del token Twitch fallita con status %d — "
                        "verifica TWITCH_CLIENT_ID/TWITCH_CLIENT_SECRET.",
                        risposta.status,
                    )
                    return None
                payload = await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Impossibile contattare l'endpoint OAuth di Twitch: %s", exc)
            return None

        analizzato = parse_app_access_token_response(payload)
        if analizzato is None:
            logger.warning("Risposta OAuth di Twitch in un formato inatteso.")
            return None

        token, scadenza_secondi = analizzato
        self._access_token = token
        self._token_expires_at = time.monotonic() + scadenza_secondi
        return token

    async def _fetch_streams(self, logins: list[str]) -> dict | None:
        token = await self._ensure_access_token()
        if token is None:
            return None

        sessione = self._get_session()
        parametri = [("user_login", login) for login in logins]
        try:
            async with sessione.get(
                self._streams_url,
                params=parametri,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Client-Id": config.TWITCH_CLIENT_ID,
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as risposta:
                if risposta.status != 200:
                    logger.warning(
                        "Richiesta a Get Streams fallita con status %d, salto questo giro.",
                        risposta.status,
                    )
                    return None
                return await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning(
                "Impossibile contattare l'API Twitch: %s — salto questo giro, "
                "riprovo al prossimo tick (%ds).",
                exc,
                TICK_SECONDS,
            )
            return None

    async def tick(self, bot: commands.Bot) -> None:
        sottoscrizioni = await twitch_subscription_repo.get_all_subscriptions()
        if not sottoscrizioni:
            return

        logins = [s.twitch_login for s in sottoscrizioni]
        # Un'unica chiamata batch per TUTTI i login sottoscritti (fino
        # a 100 per richiesta secondo i limiti Twitch), invece di una
        # chiamata per sottoscrizione — molto più leggero sui limiti
        # di rate dell'API con tanti server/streamer sottoscritti.
        payload = await self._fetch_streams(logins)
        if payload is None:
            return

        stati = parse_get_streams_response(payload, logins)
        stato_per_login = {s.login: s for s in stati}

        for sottoscrizione in sottoscrizioni:
            stato = stato_per_login.get(sottoscrizione.twitch_login)
            if stato is None:
                continue

            appena_andato_live = stato.is_live and not sottoscrizione.last_known_live
            appena_andato_offline = not stato.is_live and sottoscrizione.last_known_live

            if not (appena_andato_live or appena_andato_offline):
                continue

            await twitch_subscription_repo.update_last_known_live(
                sottoscrizione.id, stato.is_live
            )

            guild = bot.get_guild(sottoscrizione.guild_id)
            canale = guild.get_channel(sottoscrizione.channel_id) if guild else None
            if not isinstance(canale, discord.TextChannel):
                logger.warning(
                    "Canale %s non raggiungibile per la sottoscrizione Twitch #%s (server %s).",
                    sottoscrizione.channel_id,
                    sottoscrizione.id,
                    sottoscrizione.guild_id,
                )
                continue

            if appena_andato_live:
                messaggio = sottoscrizione.live_message_template.format(
                    label=sottoscrizione.label,
                    title=stato.title or "",
                    login=sottoscrizione.twitch_login,
                )
            else:
                messaggio = sottoscrizione.offline_message_template.format(
                    label=sottoscrizione.label, login=sottoscrizione.twitch_login
                )

            try:
                await canale.send(messaggio)
            except discord.HTTPException:
                logger.warning(
                    "Impossibile pubblicare l'alert Twitch nel canale %s (server %s).",
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

        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            logger.info(
                "TWITCH_CLIENT_ID/TWITCH_CLIENT_SECRET non configurati — "
                "il watcher Twitch resta inattivo finché non vengono impostati."
            )
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del Twitch watcher")

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info("Twitch watcher avviato (controllo ogni %ds).", TICK_SECONDS)


twitch_watcher = TwitchWatcherService()
