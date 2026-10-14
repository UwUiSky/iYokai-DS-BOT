"""
core/web_panel_logic.py
=======================
Regole di sicurezza del pannello web, senza rete né Discord: quando è
acceso, token e impronte delle sessioni, `state` OAuth2 firmato, token
CSRF, limite di frequenza, intestazioni di sicurezza.
Funzioni coperte: SPEC §24.1 (NF-20, issue #91)
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import OrderedDict, deque
from urllib.parse import urlencode, urlparse

LUNGHEZZA_MINIMA_CHIAVE = 32
DURATA_SESSIONE_SECONDI = 12 * 3600
DURATA_STATE_SECONDI = 600
DISCORD_AUTORIZZA = "https://discord.com/oauth2/authorize"
SCOPE = "identify"


def pannello_configurato(client_id: str, client_secret: str, chiave: str, url_pubblico: str) -> bool:
    """Acceso solo con tutte le variabili, una chiave lunga e un indirizzo http(s) valido."""
    parsed = urlparse(url_pubblico or "")
    return bool(
        client_id
        and client_secret
        and len(chiave or "") >= LUNGHEZZA_MINIMA_CHIAVE
        and parsed.scheme in ("http", "https")
        and parsed.netloc
    )


def url_redirect(url_pubblico: str) -> str:
    return url_pubblico.rstrip("/") + "/callback"


def cookie_sicuro(url_pubblico: str) -> bool:
    """Secure solo su https (in prova locale su http il browser lo scarterebbe)."""
    return urlparse(url_pubblico).scheme == "https"


def origine(url_pubblico: str) -> str:
    parsed = urlparse(url_pubblico)
    return f"{parsed.scheme}://{parsed.netloc}"


# ----------------------------------------------------------------- sessioni
def nuovo_token() -> str:
    return secrets.token_urlsafe(32)


def impronta(token: str) -> str:
    """Nel database va solo questa: chi legge la tabella non può entrare."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _firma(chiave: str, testo: str) -> str:
    return hmac.new(chiave.encode("utf-8"), testo.encode("utf-8"), hashlib.sha256).hexdigest()


def csrf_per(chiave: str, token_sessione: str) -> str:
    """Token CSRF legato alla sessione: niente da salvare."""
    return _firma(chiave, "csrf:" + token_sessione)


def csrf_valido(chiave: str, token_sessione: str, inviato: str | None) -> bool:
    return bool(inviato) and hmac.compare_digest(csrf_per(chiave, token_sessione), str(inviato))


# ------------------------------------------------------------- state OAuth2
def nuovo_state(chiave: str, adesso: float | None = None) -> tuple[str, str]:
    """(state da mettere nell'URL, valore del cookie che lo lega a questo browser)."""
    nonce = secrets.token_urlsafe(24)
    scade = int((adesso if adesso is not None else time.time()) + DURATA_STATE_SECONDI)
    corpo = f"{nonce}.{scade}"
    return nonce, f"{corpo}.{_firma(chiave, 'state:' + corpo)}"


def state_valido(chiave: str, cookie: str | None, state: str | None, adesso: float | None = None) -> bool:
    """Il cookie è nostro, non è scaduto e porta lo stesso `state` tornato da Discord."""
    if not cookie or not state:
        return False
    parti = cookie.split(".")
    if len(parti) != 3:
        return False
    nonce, scade, firma = parti
    if not hmac.compare_digest(_firma(chiave, f"state:{nonce}.{scade}"), firma):
        return False
    if not scade.isdigit() or int(scade) < (adesso if adesso is not None else time.time()):
        return False
    return hmac.compare_digest(nonce, state)


def url_autorizzazione(client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "prompt": "none",
        }
    )
    return f"{DISCORD_AUTORIZZA}?{query}"


# ----------------------------------------------------- limite di frequenza
class LimiteFrequenza:
    """Al massimo `massimo` richieste per chiave in `finestra` secondi. Memoria limitata."""

    def __init__(self, massimo: int, finestra: float, chiavi_massime: int = 10_000) -> None:
        self.massimo = massimo
        self.finestra = finestra
        self.chiavi_massime = chiavi_massime
        self._colpi: OrderedDict[str, deque] = OrderedDict()

    def consenti(self, chiave: str, adesso: float | None = None) -> bool:
        adesso = adesso if adesso is not None else time.monotonic()
        colpi = self._colpi.pop(chiave, None) or deque()
        while colpi and colpi[0] <= adesso - self.finestra:
            colpi.popleft()
        self._colpi[chiave] = colpi
        while len(self._colpi) > self.chiavi_massime:
            self._colpi.popitem(last=False)
        if len(colpi) >= self.massimo:
            return False
        colpi.append(adesso)
        return True


def ip_cliente(remoto: str | None, inoltrato: str | None) -> str:
    """
    L'IP di chi chiama. `X-Forwarded-For` vale solo se la richiesta arriva
    dal reverse proxy sulla stessa macchina; si prende l'ultimo valore,
    quello scritto dal proxy.
    """
    if remoto in ("127.0.0.1", "::1") and inoltrato:
        return inoltrato.split(",")[-1].strip() or remoto
    return remoto or "?"


# ------------------------------------------------- intestazioni di sicurezza
CSP = (
    "default-src 'none'; style-src 'self'; img-src 'self' https://cdn.discordapp.com; "
    "form-action 'self' https://discord.com; frame-ancestors 'none'; base-uri 'none'"
)


def intestazioni_sicurezza(https: bool) -> dict[str, str]:
    intestazioni = {
        "Content-Security-Policy": CSP,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        # Non "no-referrer": con quella i browser mandano `Origin: null` sui POST
        # dei moduli e il controllo dell'origine li rifiuterebbe tutti.
        "Referrer-Policy": "same-origin",
        "Cache-Control": "no-store",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    if https:
        intestazioni["Strict-Transport-Security"] = "max-age=31536000"
    return intestazioni
