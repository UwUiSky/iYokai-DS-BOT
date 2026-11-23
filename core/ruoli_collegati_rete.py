"""
core/ruoli_collegati_rete.py
============================
Le chiamate di rete dei ruoli collegati (ALR-049): token e profilo di Twitch, token, utente e collegamento di Discord,
registrazione dei metadati dell'applicazione. Ogni chiamata ha un limite di tempo e ritorna None/False se qualcosa va
storto: mai un'eccezione, mai un segreto nei log (si scrive solo il codice di risposta). I test mettono un finto al posto
di questa classe.
Funzioni coperte: SPEC §24.9 (ALR-049, issue #129), §24.11 (VER-027)
Dipende da: core/ruoli_collegati_logic.py
"""

from __future__ import annotations

import json
import logging

import aiohttp

from core.ruoli_collegati_logic import TokenOAuth, scade_tra

logger = logging.getLogger("iyokai.ruoli_collegati")

URL_TWITCH_TOKEN = "https://id.twitch.tv/oauth2/token"
URL_TWITCH_UTENTI = "https://api.twitch.tv/helix/users"
URL_DISCORD_API = "https://discord.com/api/v10"
RISORSA_COLLEGAMENTO = "role" + "-connection"  # nome della risorsa di Discord
TEMPO_MASSIMO = 10  # secondi per chiamata
DIMENSIONE_MASSIMA = 64 * 1024


class ReteRuoliCollegati:
    def __init__(self, *, twitch_id: str, twitch_segreto: str, discord_id: str, discord_segreto: str, token_bot: str) -> None:
        self._twitch_id, self._twitch_segreto = twitch_id, twitch_segreto
        self._discord_id, self._discord_segreto = discord_id, discord_segreto
        self._token_bot = token_bot

    async def _chiama(self, metodo: str, url: str, **kw):
        """(stato, JSON o None). Un errore di rete o una risposta troppo grande valgono (0, None)."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TEMPO_MASSIMO)) as sessione:
                async with sessione.request(metodo, url, **kw) as risposta:
                    corpo = await risposta.content.read(DIMENSIONE_MASSIMA + 1)
                    if len(corpo) > DIMENSIONE_MASSIMA:
                        return 0, None
                    try:
                        return risposta.status, json.loads(corpo) if corpo else None
                    except ValueError:
                        return risposta.status, None
        except (aiohttp.ClientError, TimeoutError):
            logger.warning("Ruoli collegati: nessuna risposta da %s.", url.split("?")[0].split("/")[2])
            return 0, None

    @staticmethod
    def _token(payload) -> TokenOAuth | None:
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
            return None
        refresh = payload.get("refresh_token")
        return TokenOAuth(payload["access_token"], refresh if isinstance(refresh, str) else None, scade_tra(payload.get("expires_in")))

    async def twitch_scambia(self, code: str, redirect_uri: str) -> TokenOAuth | None:
        stato, payload = await self._chiama(
            "POST", URL_TWITCH_TOKEN,
            data={"client_id": self._twitch_id, "client_secret": self._twitch_segreto, "code": code,
                  "grant_type": "authorization_code", "redirect_uri": redirect_uri},
        )
        if stato != 200:
            logger.warning("Ruoli collegati: Twitch ha rifiutato il codice (stato %s).", stato)
            return None
        return self._token(payload)

    async def twitch_utente(self, access_token: str) -> dict | None:
        stato, payload = await self._chiama(
            "GET", URL_TWITCH_UTENTI, headers={"Authorization": f"Bearer {access_token}", "Client-Id": self._twitch_id}
        )
        return payload if stato == 200 and isinstance(payload, dict) else None

    async def discord_scambia(self, code: str, redirect_uri: str) -> TokenOAuth | None:
        stato, payload = await self._chiama(
            "POST", f"{URL_DISCORD_API}/oauth2/token",
            data={"client_id": self._discord_id, "client_secret": self._discord_segreto, "code": code,
                  "grant_type": "authorization_code", "redirect_uri": redirect_uri},
        )
        if stato != 200:
            logger.warning("Ruoli collegati: Discord ha rifiutato il codice (stato %s).", stato)
            return None
        return self._token(payload)

    async def discord_utente(self, access_token: str) -> int | None:
        stato, payload = await self._chiama(
            "GET", f"{URL_DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {access_token}"}
        )
        try:
            return int(payload["id"]) if stato == 200 else None
        except (KeyError, TypeError, ValueError):
            return None

    async def discord_profilo(self, access_token: str) -> tuple[int, bool] | None:
        """(ID, ha un avatar suo) dell'utente del token, o None. Dell'avatar si legge solo se c'è: mai l'indirizzo."""
        stato, payload = await self._chiama(
            "GET", f"{URL_DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {access_token}"}
        )
        try:
            return (int(payload["id"]), bool(payload.get("avatar"))) if stato == 200 else None
        except (KeyError, TypeError, ValueError, AttributeError):
            return None

    async def discord_rinnova(self, refresh_token: str) -> TokenOAuth | None:
        stato, payload = await self._chiama(
            "POST", f"{URL_DISCORD_API}/oauth2/token",
            data={"client_id": self._discord_id, "client_secret": self._discord_segreto, "refresh_token": refresh_token,
                  "grant_type": "refresh_token"},
        )
        if stato != 200:
            logger.warning("Ruoli collegati: Discord non ha rinnovato il token (stato %s).", stato)
            return None
        return self._token(payload)

    async def discord_scrivi_stato(self, access_token: str, corpo: dict) -> int:
        """Come `discord_scrivi_collegamento`, ma ritorna il codice (401: il token non vale più; 429: troppe richieste)."""
        stato, _ = await self._chiama(
            "PUT", f"{URL_DISCORD_API}/users/@me/applications/{self._discord_id}/{RISORSA_COLLEGAMENTO}",
            headers={"Authorization": f"Bearer {access_token}"}, json=corpo,
        )
        if stato != 200:
            logger.warning("Ruoli collegati: Discord non ha accettato il collegamento (stato %s).", stato)
        return stato

    async def discord_scrivi_collegamento(self, access_token: str, corpo: dict) -> bool:
        return await self.discord_scrivi_stato(access_token, corpo) == 200

    # ---- giro periodico (D127): il codice di ritorno dice se il token è revocato o se è un guasto passeggero
    @staticmethod
    def _esito(stato: int) -> str:
        """«ok», «revocato» (400: il refresh token non vale più), «limite» (429) o «errore» (rete, 5xx, 401 = chiavi nostre)."""
        return {200: "ok", 400: "revocato", 429: "limite"}.get(stato, "errore")

    async def twitch_rinnova(self, refresh_token: str) -> tuple[TokenOAuth | None, str]:
        stato, payload = await self._chiama(
            "POST", URL_TWITCH_TOKEN,
            data={"client_id": self._twitch_id, "client_secret": self._twitch_segreto, "refresh_token": refresh_token,
                  "grant_type": "refresh_token"},
        )
        esito = self._esito(stato)
        token = self._token(payload) if esito == "ok" else None
        return token, ("ok" if token else ("errore" if esito == "ok" else esito))

    async def discord_rinnova_esito(self, refresh_token: str) -> tuple[TokenOAuth | None, str]:
        stato, payload = await self._chiama(
            "POST", f"{URL_DISCORD_API}/oauth2/token",
            data={"client_id": self._discord_id, "client_secret": self._discord_segreto, "refresh_token": refresh_token,
                  "grant_type": "refresh_token"},
        )
        esito = self._esito(stato)
        token = self._token(payload) if esito == "ok" else None
        return token, ("ok" if token else ("errore" if esito == "ok" else esito))

    async def twitch_utente_stato(self, access_token: str) -> tuple[dict | None, int]:
        stato, payload = await self._chiama(
            "GET", URL_TWITCH_UTENTI, headers={"Authorization": f"Bearer {access_token}", "Client-Id": self._twitch_id}
        )
        return (payload if stato == 200 and isinstance(payload, dict) else None), stato

    # ---- connessioni del profilo (D127): solo con il consenso OAuth `connections`; si leggono i tipi, mai i nomi
    async def discord_connessioni(self, access_token: str) -> list[str] | None:
        stato, payload = await self._chiama(
            "GET", f"{URL_DISCORD_API}/users/@me/connections", headers={"Authorization": f"Bearer {access_token}"}
        )
        if stato != 200 or not isinstance(payload, list):
            return None
        return [v["type"] for v in payload if isinstance(v, dict) and isinstance(v.get("type"), str)][:100]

    async def discord_revoca(self, access_token: str) -> bool:
        """Il token delle connessioni non serve più dopo la lettura: si revoca (al meglio)."""
        stato, _ = await self._chiama(
            "POST", f"{URL_DISCORD_API}/oauth2/token/revoke",
            data={"client_id": self._discord_id, "client_secret": self._discord_segreto, "token": access_token,
                  "token_type_hint": "access_token"},
        )
        return stato == 200

    async def registra_metadati(self, metadati: list[dict]) -> bool:
        if not self._token_bot:
            return False
        stato, _ = await self._chiama(
            "PUT", f"{URL_DISCORD_API}/applications/{self._discord_id}/{RISORSA_COLLEGAMENTO}s/metadata",
            headers={"Authorization": f"Bot {self._token_bot}"}, json=metadati,
        )
        if stato != 200:
            logger.warning("Ruoli collegati: metadati non registrati (stato %s).", stato)
        return stato == 200
