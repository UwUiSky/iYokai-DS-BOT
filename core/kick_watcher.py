"""
core/kick_watcher.py
====================
Controlla le dirette su Kick (NF-32, SPEC §10.13): stesso schema di
core/twitch_watcher.py, con l'API pubblica di Kick (token «client credentials»
da KICK_CLIENT_ID e KICK_CLIENT_SECRET, gratuiti). Una richiesta ogni 50
canali; senza le due variabili il watcher resta inattivo. Si avvia da main.py.
Funzioni coperte: SPEC §10.13 (NF-32)
"""

from __future__ import annotations

import logging
import os
import time

import aiohttp
from discord.ext import commands, tasks

from core.alert_options_logic import AlertOptions
from core.bot_ready import attendi_bot_pronto
from core.feed_alert_gate import AvvisoUnaVolta, filtra_attive
from core.kick_api_logic import (
    MAX_SLUG_PER_RICHIESTA,
    parse_channels_response,
    parse_token_response,
)
from core.live_alert_flow import carica_contesto, pubblica_cambio_live
from core.repositories.kick_subscription_repo import kick_subscription_repo
from core.template_renderer import render_template

logger = logging.getLogger("iyokai.kick_watcher")

KIND = "KK"
TICK_SECONDS = 120
REQUEST_TIMEOUT_SECONDS = 15
KICK_OAUTH_URL = "https://id.kick.com/oauth/token"
KICK_CHANNELS_URL = "https://api.kick.com/public/v1/channels"
TOKEN_REFRESH_MARGIN_SECONDS = 60


def credenziali() -> tuple[str, str]:
    return os.environ.get("KICK_CLIENT_ID", ""), os.environ.get("KICK_CLIENT_SECRET", "")


class KickWatcherService:
    def __init__(self, oauth_url: str = KICK_OAUTH_URL, channels_url: str = KICK_CHANNELS_URL) -> None:
        self._loop_task: tasks.Loop | None = None
        self._avvisi = AvvisoUnaVolta()
        self._http_session: aiohttp.ClientSession | None = None
        self._oauth_url, self._channels_url = oauth_url, channels_url
        self._access_token: str | None = None
        self._token_expires_at: float | None = None

    def _sessione(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def _token(self) -> str | None:
        client_id, secret = credenziali()
        if not client_id or not secret:
            return None
        if (
            self._access_token is not None and self._token_expires_at is not None
            and time.monotonic() < self._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS
        ):
            return self._access_token
        try:
            async with self._sessione().post(
                self._oauth_url,
                data={"client_id": client_id, "client_secret": secret, "grant_type": "client_credentials"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as r:
                if r.status != 200:
                    logger.warning("Token Kick rifiutato (status %d): controlla KICK_CLIENT_ID/KICK_CLIENT_SECRET.", r.status)
                    return None
                payload = await r.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Kick non raggiungibile per il token: %s", exc)
            return None
        analizzato = parse_token_response(payload)
        if analizzato is None:
            logger.warning("Risposta del token Kick in un formato inatteso.")
            return None
        self._access_token, scade = analizzato
        self._token_expires_at = time.monotonic() + scade
        return self._access_token

    async def _fetch_channels(self, slugs: list[str]):
        token = await self._token()
        if token is None:
            return None
        try:
            async with self._sessione().get(
                self._channels_url,
                params=[("slug", s) for s in slugs],
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as r:
                if r.status == 401:
                    self._access_token = self._token_expires_at = None
                    logger.warning("Token Kick scaduto (401): ne chiedo uno nuovo al prossimo giro.")
                    return None
                if r.status != 200:
                    logger.warning("Richiesta ai canali Kick fallita (status %d), salto il giro.", r.status)
                    return None
                return await r.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("API Kick non raggiungibile: %s — riprovo al prossimo giro.", exc)
            return None

    async def tick(self, bot: commands.Bot) -> None:
        sottoscrizioni = await filtra_attive(await kick_subscription_repo.get_all_subscriptions())
        if not sottoscrizioni:
            return
        slugs = list(dict.fromkeys(s.kick_slug.lower() for s in sottoscrizioni))
        stati = {}
        for i in range(0, len(slugs), MAX_SLUG_PER_RICHIESTA):
            blocco = slugs[i : i + MAX_SLUG_PER_RICHIESTA]
            payload = await self._fetch_channels(blocco)
            if payload is None:
                continue
            for stato in parse_channels_response(payload, blocco):
                stati[stato.slug] = stato

        opzioni, ruoli = await carica_contesto(KIND, sottoscrizioni)
        for sub in sottoscrizioni:
            stato = stati.get(sub.kick_slug.lower())
            if stato is None or stato.is_live == sub.last_known_live:
                continue
            if stato.is_live:
                testo = render_template(
                    sub.live_message_template,
                    {"label": sub.label, "title": stato.title or "", "login": sub.kick_slug,
                     "game": stato.category or ""},
                )
            else:
                testo = render_template(sub.offline_message_template, {"label": sub.label, "login": sub.kick_slug})
            await pubblica_cambio_live(
                bot, sub, KIND, in_diretta=stato.is_live, testo=testo,
                url=f"https://kick.com/{sub.kick_slug}", opz=opzioni.get(sub.id, AlertOptions()),
                ruolo_live_id=ruoli.get(sub.guild_id), repo_stato=kick_subscription_repo,
                avvisi=self._avvisi, nome="Kick",
                titolo=stato.title or "", gioco=stato.category or "",
            )

    async def close(self) -> None:
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None
        if self._loop_task is not None:
            self._loop_task.cancel()
            self._loop_task = None

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return
        client_id, secret = credenziali()
        if not client_id or not secret:
            logger.info("KICK_CLIENT_ID/KICK_CLIENT_SECRET non configurati: il watcher Kick resta inattivo.")
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del Kick watcher")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Kick watcher avviato (controllo ogni %ds).", TICK_SECONDS)


kick_watcher = KickWatcherService()
