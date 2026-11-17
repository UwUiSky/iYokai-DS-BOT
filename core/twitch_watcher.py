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
from discord.ext import commands, tasks

from core.alert_frequenze_logic import intervallo
from core.bot_ready import attendi_bot_pronto
from core.config import config
from core.feed_alert_gate import AvvisoUnaVolta, filtra_attive
from core.alert_options_logic import AlertOptions
from core.live_alert_flow import carica_contesto, pubblica_cambio_live
from core.alert_messaggio_logic import pulisci_esterno
from core.template_renderer import render_template
from core.twitch_api_logic import (
    parse_app_access_token_response,
    parse_get_streams_response,
    parse_schedule_response,
    parse_users_response,
    parse_videos_response,
)
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
# LIM-46: Get Streams accetta al massimo 100 login per richiesta e
# restituisce 20 stream per pagina se `first` non è indicato.
MAX_LOGIN_PER_RICHIESTA = 100


class TwitchWatcherService:
    def __init__(
        self,
        oauth_url: str = TWITCH_OAUTH_URL,
        streams_url: str = TWITCH_STREAMS_URL,
    ) -> None:
        self._loop_task: tasks.Loop | None = None
        self._avvisi = AvvisoUnaVolta()
        self._http_session: aiohttp.ClientSession | None = None
        self._oauth_url = oauth_url
        self._streams_url = streams_url
        self._access_token: str | None = None
        self._token_expires_at: float | None = None  # time.monotonic()
        self._ids: dict[str, str] = {}

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
        parametri.append(("first", str(MAX_LOGIN_PER_RICHIESTA)))
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
                if risposta.status == 401:
                    # Token revocato o scaduto prima del previsto: lo
                    # buttiamo, il prossimo giro ne chiede uno nuovo.
                    self._access_token = None
                    self._token_expires_at = None
                    logger.warning("Token Twitch rifiutato (401): ne chiedo uno nuovo al prossimo giro.")
                    return None
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

    async def _helix(self, percorso: str, parametri: list[tuple[str, str]]) -> dict | None:
        """Una richiesta GET a un altro punto dell'API (utenti, registrazioni, calendario). None se non risponde."""
        token = await self._ensure_access_token()
        if token is None:
            return None
        try:
            async with self._get_session().get(
                f"{self._streams_url.rsplit('/', 1)[0]}/{percorso}",
                params=parametri,
                headers={"Authorization": f"Bearer {token}", "Client-Id": config.TWITCH_CLIENT_ID},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as risposta:
                if risposta.status == 401:
                    self._access_token = None
                    self._token_expires_at = None
                    return None
                if risposta.status != 200:
                    return None
                return await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("API Twitch (%s) non raggiungibile: %s", percorso, exc)
            return None

    async def utente_id(self, login: str) -> str | None:
        """ID numerico di un canale (ricordato: un utente Twitch non cambia ID)."""
        login = login.lower()
        if login in self._ids:
            return self._ids[login]
        id_utente = parse_users_response(await self._helix("users", [("login", login)]))
        if id_utente is not None:
            if len(self._ids) >= 500:
                self._ids.pop(next(iter(self._ids)))
            self._ids[login] = id_utente
        return id_utente

    async def ultimo_vod(self, login: str) -> str:
        """ALR-012: indirizzo dell'ultima registrazione del canale (due richieste, solo a fine diretta); vuoto se non c'è."""
        id_utente = await self.utente_id(login)
        if id_utente is None:
            return ""
        payload = await self._helix("videos", [("user_id", id_utente), ("type", "archive"), ("first", "1")])
        return parse_videos_response(payload) or ""

    async def calendario(self, login: str) -> list:
        """ALR-013: i prossimi segmenti del calendario (una richiesta, più l'ID se non lo conosciamo)."""
        id_utente = await self.utente_id(login)
        if id_utente is None:
            return []
        return parse_schedule_response(await self._helix("schedule", [("broadcaster_id", id_utente), ("first", "10")]))

    async def tick(self, bot: commands.Bot) -> None:
        sottoscrizioni = await twitch_subscription_repo.get_all_subscriptions()
        # LC-7: server con il modulo spento = nessuna richiesta, nessun messaggio.
        sottoscrizioni = await filtra_attive(sottoscrizioni)
        if not sottoscrizioni:
            return

        # Login unici (lo stesso streamer può essere seguito da più
        # server), in blocchi da 100: una richiesta per blocco.
        logins = list(dict.fromkeys(s.twitch_login.lower() for s in sottoscrizioni))
        stato_per_login = {}
        for i in range(0, len(logins), MAX_LOGIN_PER_RICHIESTA):
            blocco = logins[i : i + MAX_LOGIN_PER_RICHIESTA]
            payload = await self._fetch_streams(blocco)
            if payload is None:
                continue  # le sottoscrizioni di questo blocco restano com'erano
            for stato in parse_get_streams_response(payload, blocco):
                stato_per_login[stato.login] = stato

        opzioni, ruoli = await carica_contesto("TW", sottoscrizioni)
        for sottoscrizione in sottoscrizioni:
            stato = stato_per_login.get(sottoscrizione.twitch_login.lower())
            if stato is None:
                continue

            appena_andato_live = stato.is_live and not sottoscrizione.last_known_live
            appena_andato_offline = not stato.is_live and sottoscrizione.last_known_live

            if not (appena_andato_live or appena_andato_offline):
                continue

            valori = None
            if appena_andato_live:
                valori = {
                    "label": sottoscrizione.label,
                    "title": pulisci_esterno(stato.title),
                    "login": sottoscrizione.twitch_login,
                    "game": pulisci_esterno(stato.game_name, 100),
                    "gioco": pulisci_esterno(stato.game_name, 100),  # ALR-022
                }
                valori["descrizione"] = f"🎮 {valori['game']}" if valori["game"] else ""
                messaggio = render_template(sottoscrizione.live_message_template, valori)
            else:
                valori_fine = {"label": sottoscrizione.label, "login": sottoscrizione.twitch_login, "vod": ""}
                if "{vod}" in sottoscrizione.offline_message_template:  # ALR-012: la registrazione, solo se richiesta
                    valori_fine["vod"] = await self.ultimo_vod(sottoscrizione.twitch_login)
                messaggio = render_template(sottoscrizione.offline_message_template, valori_fine)

            await pubblica_cambio_live(
                bot, sottoscrizione, "TW",
                in_diretta=stato.is_live, testo=messaggio,
                url=f"https://twitch.tv/{sottoscrizione.twitch_login}",
                opz=opzioni.get(sottoscrizione.id, AlertOptions()),
                ruolo_live_id=ruoli.get(sottoscrizione.guild_id),
                repo_stato=twitch_subscription_repo,
                avvisi=self._avvisi, nome="Twitch",
                titolo=stato.title or "", gioco=stato.game_name or "", valori=valori,
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

        @tasks.loop(seconds=intervallo("twitch"))  # ALR-034: da .env, con minimo
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del Twitch watcher")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Twitch watcher avviato (controllo ogni %ds).", intervallo("twitch"))


twitch_watcher = TwitchWatcherService()
