"""
core/restore_orchestrator.py
================================
Le due sole chiamate di rete REALI del restore utenti via OAuth2
(SPEC.md §11.11) — scambio del `code` per un token, e l'aggiunta
effettiva dell'utente al server tramite l'endpoint "Add Guild
Member" di Discord (questo È il meccanismo `guilds.join`: un bot con
il proprio token PUT-a un utente in un server usando l'access_token
OAuth2 che quell'utente ha appena concesso).

Rispetta i limiti di frequenza: su un 429 attende il ``Retry-After`` e riprova
(M 12.11). Rinnova i token scaduti con ``grant_type=refresh_token`` (M 12.10).
Funzioni coperte: SPEC §11.11, M 12.10, M 12.11

Isolato in una classe con URL base iniettabili (stesso pattern di
TwitchWatcherService) così i test possono puntare a un server aiohttp
finto locale invece che a Discord vero — la rete del sandbox di
sviluppo non raggiunge Discord comunque (vedi PROGRESS.md).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import aiohttp

logger = logging.getLogger("iyokai.restore_orchestrator")

DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_BASE_URL = "https://discord.com/api/v10"

REQUEST_TIMEOUT_SECONDS = 15

# M 12.11 (LIM-7): tentativi dopo un 429 e attesa massima accettata.
MAX_TENTATIVI_429 = 3
ATTESA_MASSIMA_SECONDI = 60.0


@dataclass(frozen=True)
class ExchangedToken:
    # SEC-16: repr=False — un log di debug con questo oggetto non deve
    # stampare le credenziali OAuth altrui in chiaro.
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: datetime


class RestoreOrchestrator:
    def __init__(
        self,
        token_url: str = DISCORD_TOKEN_URL,
        api_base_url: str = DISCORD_API_BASE_URL,
        sleep=asyncio.sleep,
    ) -> None:
        self._sleep = sleep
        self._http_session: aiohttp.ClientSession | None = None
        self._token_url = token_url
        self._api_base_url = api_base_url

    def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self) -> None:
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None

    async def _put_con_attesa(self, url: str, **kwargs) -> int:
        """PUT che su un 429 attende il Retry-After e riprova (poi restituisce 429)."""
        sessione = self._get_session()
        stato = 0
        for tentativo in range(MAX_TENTATIVI_429):
            async with sessione.put(
                url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS), **kwargs
            ) as risposta:
                stato = risposta.status
                if stato != 429:
                    return stato
                try:
                    attesa = float(risposta.headers.get("Retry-After", "1"))
                except ValueError:
                    attesa = 1.0
            if tentativo + 1 < MAX_TENTATIVI_429:
                await self._sleep(min(max(attesa, 0.0), ATTESA_MASSIMA_SECONDI))
        return stato

    async def refresh_access_token(
        self, client_id: str, client_secret: str, refresh_token: str
    ) -> ExchangedToken | None:
        """
        Rinnova un token scaduto o vicino alla scadenza (M 12.10, LIM-37).
        None se Discord rifiuta (token revocato) o la rete non risponde: il
        chiamante ripiega sulla richiesta di consenso.
        """
        return await self._richiedi_token(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )

    async def exchange_code_for_token(
        self, client_id: str, client_secret: str, redirect_uri: str, code: str
    ) -> ExchangedToken | None:
        """
        Scambia il `code` ricevuto dalla callback OAuth2 con un
        access_token + refresh_token. None se Discord rifiuta la
        richiesta (code scaduto/già usato/client sbagliato) o la
        rete non risponde — il chiamante (il web server della
        callback) mostra un errore all'utente in quel caso, non
        salva nulla.
        """
        return await self._richiedi_token(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            }
        )

    async def _richiedi_token(self, dati: dict) -> ExchangedToken | None:
        sessione = self._get_session()
        try:
            async with sessione.post(
                self._token_url,
                data=dati,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as risposta:
                if risposta.status != 200:
                    logger.warning(
                        "Richiesta token OAuth2 (%s) fallita con status %d.",
                        dati.get("grant_type"),
                        risposta.status,
                    )
                    return None
                payload = await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Impossibile contattare l'endpoint token di Discord: %s", exc)
            return None

        try:
            scadenza = datetime.now(timezone.utc) + timedelta(seconds=int(payload["expires_in"]))
            return ExchangedToken(
                access_token=payload["access_token"],
                refresh_token=payload["refresh_token"],
                expires_at=scadenza,
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Risposta token OAuth2 di Discord in un formato inatteso.")
            return None

    async def fetch_current_user(self, access_token: str) -> int | None:
        """
        SEC-3: chiama `GET /users/@me` con l'access_token appena
        ottenuto dallo scambio del code — l'UNICA fonte affidabile
        per sapere CHI ha davvero autorizzato (mai fidarsi di un
        user_id scritto nello state, che è solo un URL: chiunque
        potrebbe scriverne uno diverso dal proprio prima di
        cliccare). None se Discord rifiuta il token o la rete non
        risponde.
        """
        sessione = self._get_session()
        url = f"{self._api_base_url}/users/@me"
        try:
            async with sessione.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as risposta:
                if risposta.status != 200:
                    logger.warning(
                        "GET /users/@me fallito dopo lo scambio del code (status %d).",
                        risposta.status,
                    )
                    return None
                payload = await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Impossibile contattare /users/@me di Discord: %s", exc)
            return None

        try:
            return int(payload["id"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Risposta /users/@me di Discord in un formato inatteso.")
            return None

    async def assign_role(self, bot_token: str, guild_id: int, user_id: int, role_id: int) -> bool:
        """
        Assegna un ruolo (tipicamente quello di verificato) all'utente
        appena aggiunto al server — stesso endpoint REST usato da
        join_user_via_oauth, stavolta su /roles/{role_id}. True su
        successo (204); False altrimenti — un errore qui non deve
        bloccare il restore, l'utente è comunque già DENTRO al
        server, semplicemente resta da verificare a mano.
        """
        url = f"{self._api_base_url}/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
        try:
            stato = await self._put_con_attesa(url, headers={"Authorization": f"Bot {bot_token}"})
            return stato == 204
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Impossibile assegnare il ruolo verificato dopo il restore: %s", exc)
            return False

    async def join_user_via_oauth(
        self, bot_token: str, guild_id: int, user_id: int, access_token: str
    ) -> bool:
        """
        Aggiunge l'utente al server — il vero "guilds.join". True se
        l'utente è stato aggiunto ORA (201) o era già membro (204,
        Discord lo considera comunque un successo: l'obiettivo "è
        nel server" è raggiunto); False su qualunque altro esito
        (token scaduto/revocato, bot senza permessi, server sparito).
        """
        url = f"{self._api_base_url}/guilds/{guild_id}/members/{user_id}"
        try:
            stato = await self._put_con_attesa(
                url,
                headers={"Authorization": f"Bot {bot_token}"},
                json={"access_token": access_token},
            )
            if stato in (201, 204):
                return True
            logger.warning(
                "guilds.join fallito per utente %s nel server %s (status %d).",
                user_id,
                guild_id,
                stato,
            )
            return False
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Impossibile contattare l'endpoint guilds.join di Discord: %s", exc)
            return False


restore_orchestrator = RestoreOrchestrator()
