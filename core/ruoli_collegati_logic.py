"""
core/ruoli_collegati_logic.py
=============================
Ruoli collegati (Linked Roles) di Discord per affiliati e partner Twitch (ALR-049) e per la verifica del server
(VER-027, D111): configurazione, `state` firmato a scadenza breve e monouso, indirizzi di autorizzazione, metadati
dell'applicazione, lettura delle risposte di Twitch e corpo del collegamento (che unisce i valori di Twitch e della
verifica: Discord tiene un solo collegamento per persona e applicazione). Niente rete qui: la rete sta in
`core/ruoli_collegati_rete.py` (si sostituisce nei test).
I token si cifrano con `core/oauth_crypto` (AES-256-GCM) e legati all'utente e al campo (dati aggiuntivi autenticati).
Funzioni coperte: SPEC §24.9 (ALR-049, issue #129), §24.11 (VER-027, issue #118)
Dipende da: core/oauth_crypto.py
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from core import oauth_crypto

SCOPE_TWITCH = ""  # niente permessi in più: serve solo sapere chi sei e che tipo di canale hai
SCOPE_DISCORD = "identify role_connections.write"
URL_TWITCH_AUTORIZZA = "https://id.twitch.tv/oauth2/authorize"
URL_DISCORD_AUTORIZZA = "https://discord.com/oauth2/authorize"
DURATA_STATE_SECONDI = 600
PIATTAFORMA = "Twitch"
CHIAVE_AFFILIATO = "twitch_affiliato"
CHIAVE_PARTNER = "twitch_partner"
TIPO_BOOLEANO = 7  # BOOLEAN_EQUAL dei metadati di Discord
SCOPO_TWITCH = "tw"
SCOPO_DISCORD = "dc"
SCOPO_VERIFICA = "vf"  # VER-027: stesso indirizzo di ritorno di Discord, `state` di un altro scopo
PIATTAFORMA_VERIFICA = "iYokai"
CHIAVE_VERIFICA = "verifica_superata"
CHIAVE_ETA = "eta_account_giorni"
CHIAVE_AVATAR = "avatar_presente"
TIPO_INTERO_MINIMO = 2  # INTEGER_GREATER_THAN_OR_EQUAL dei metadati di Discord


@dataclass(frozen=True)
class Configurazione:
    twitch_id: str = ""
    twitch_segreto: str = field(default="", repr=False)
    chiave_cifratura: str = field(default="", repr=False)
    token_bot: str = field(default="", repr=False)

    def mancanti(self) -> list[str]:
        """I nomi delle impostazioni che mancano (mai i valori)."""
        nomi = (
            ("TWITCH_CLIENT_ID", self.twitch_id), ("TWITCH_CLIENT_SECRET", self.twitch_segreto),
            ("OAUTH_ENCRYPTION_KEY", self.chiave_cifratura),
        )
        return [n for n, v in nomi if not v]

    @property
    def pronta(self) -> bool:
        return not self.mancanti()

    @property
    def twitch_pronto(self) -> bool:
        return self.pronta

    @property
    def verifica_pronta(self) -> bool:
        """La verifica (VER-027) non usa Twitch: servono solo la chiave di cifratura e il bot per registrare i metadati."""
        return bool(self.chiave_cifratura)


def leggi_configurazione() -> Configurazione:
    from core.config import config

    return Configurazione(
        twitch_id=config.TWITCH_CLIENT_ID, twitch_segreto=config.TWITCH_CLIENT_SECRET,
        chiave_cifratura=config.OAUTH_ENCRYPTION_KEY, token_bot=config.YOKAI_BOT_TOKEN,
    )


# ------------------------------------------------------------ state firmato
def _firma(chiave: str, corpo: bytes) -> str:
    return hmac.new(hashlib.sha256(("alr49:" + chiave).encode()).digest(), corpo, hashlib.sha256).hexdigest()


def crea_state(chiave: str, user_id: int, scopo: str, *, ora: float | None = None) -> str:
    corpo = json.dumps(
        {"s": scopo, "u": user_id, "e": (time.time() if ora is None else ora) + DURATA_STATE_SECONDI,
         "n": base64.urlsafe_b64encode(os.urandom(12)).decode()},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(corpo).decode() + "." + _firma(chiave, corpo)


_USATI: dict[str, float] = {}  # nonce -> scadenza: lo state vale una volta sola (un solo processo)


def verifica_state(chiave: str, raw: str | None, scopo: str, *, ora: float | None = None, consuma: bool = True) -> int | None:
    """L'utente dello state, o None se manomesso, scaduto, di un altro scopo o già usato. Mai un'eccezione."""
    if not raw or "." not in raw or len(raw) > 600:
        return None
    adesso = time.time() if ora is None else ora
    corpo_b64, _, firma = raw.partition(".")
    try:
        corpo = base64.urlsafe_b64decode(corpo_b64 + "=" * (-len(corpo_b64) % 4))
        if not hmac.compare_digest(_firma(chiave, corpo), firma):
            return None
        dati = json.loads(corpo)
        if dati["s"] != scopo or float(dati["e"]) <= adesso:
            return None
        utente, nonce, scade = int(dati["u"]), str(dati["n"]), float(dati["e"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    for vecchio in [n for n, e in _USATI.items() if e <= adesso]:
        del _USATI[vecchio]
    if nonce in _USATI:
        return None
    if consuma:
        _USATI[nonce] = scade
    return utente


# ------------------------------------------------------------- indirizzi
def url_twitch(twitch_id: str, redirect_uri: str, state: str) -> str:
    query = {"client_id": twitch_id, "redirect_uri": redirect_uri, "response_type": "code", "state": state, "force_verify": "true"}
    if SCOPE_TWITCH:
        query["scope"] = SCOPE_TWITCH
    return f"{URL_TWITCH_AUTORIZZA}?{urlencode(query)}"


def url_discord(discord_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {"client_id": discord_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE_DISCORD,
         "state": state, "prompt": "consent"}
    )
    return f"{URL_DISCORD_AUTORIZZA}?{query}"


# -------------------------------------------------------------- metadati
def metadati_applicazione(con_twitch: bool = True) -> list[dict]:
    """
    I campi registrati sull'applicazione (massimo 5, nome fino a 100 caratteri, descrizione fino a 200): i due booleani
    di Twitch (se è configurato) e i tre della verifica. Discord li mostra nelle impostazioni del ruolo.
    """
    twitch = [
        {"key": CHIAVE_AFFILIATO, "name": "Affiliato Twitch", "description": "Ha un canale Twitch affiliato", "type": TIPO_BOOLEANO,
         "name_localizations": {"en-US": "Twitch affiliate"}, "description_localizations": {"en-US": "Has an affiliate Twitch channel"}},
        {"key": CHIAVE_PARTNER, "name": "Partner Twitch", "description": "Ha un canale Twitch partner", "type": TIPO_BOOLEANO,
         "name_localizations": {"en-US": "Twitch partner"}, "description_localizations": {"en-US": "Has a partner Twitch channel"}},
    ]
    verifica = [
        {"key": CHIAVE_VERIFICA, "name": "Verifica superata", "description": "Ha superato la verifica di un server con iYokai", "type": TIPO_BOOLEANO,
         "name_localizations": {"en-US": "Verification passed"}, "description_localizations": {"en-US": "Passed verification in a server using iYokai"}},
        {"key": CHIAVE_ETA, "name": "Età dell'account (giorni)", "description": "Giorni dalla creazione dell'account Discord (almeno)", "type": TIPO_INTERO_MINIMO,
         "name_localizations": {"en-US": "Account age (days)"}, "description_localizations": {"en-US": "Days since the Discord account was created (at least)"}},
        {"key": CHIAVE_AVATAR, "name": "Avatar presente", "description": "L'account ha un avatar suo", "type": TIPO_BOOLEANO,
         "name_localizations": {"en-US": "Avatar set"}, "description_localizations": {"en-US": "The account has its own avatar"}},
    ]
    return (twitch if con_twitch else []) + verifica


def eta_giorni(user_id: int, *, ora: float | None = None) -> int:
    """Giorni dalla creazione dell'account, ricavati dall'ID (nessun dato in più da chiedere a Discord)."""
    creato = ((int(user_id) >> 22) + 1420070400000) / 1000
    return max(0, int(((time.time() if ora is None else ora) - creato) // 86400))


def tipo_canale(valore: object) -> str:
    """«affiliate», «partner» o vuoto: tutto il resto vale «nessuno» (non ci si fida del testo di Twitch)."""
    return valore if valore in ("affiliate", "partner") else ""


def corpo_collegamento(
    login: str, tipo: str, *, verifica: tuple[bool, int, bool] | None = None, con_twitch: bool = True
) -> dict:
    """
    Il corpo del collegamento (Discord ne tiene uno per persona e applicazione: ogni scrittura lo sostituisce tutto).
    Twitch: il nome del canale (al massimo 100 caratteri) e i due booleani. Verifica, se la persona l'ha collegata:
    (verifica superata, età in giorni, avatar presente). Senza verifica il corpo è quello di sempre.
    """
    metadati: dict = {}
    if con_twitch:
        metadati.update({CHIAVE_AFFILIATO: tipo == "affiliate", CHIAVE_PARTNER: tipo == "partner"})
    if verifica is not None:
        superata, giorni, avatar = verifica
        metadati.update({CHIAVE_VERIFICA: bool(superata), CHIAVE_ETA: max(0, int(giorni)), CHIAVE_AVATAR: bool(avatar)})
    corpo = {"platform_name": PIATTAFORMA if con_twitch else PIATTAFORMA_VERIFICA, "metadata": metadati}
    if con_twitch or (login or ""):
        corpo["platform_username"] = (login or "")[:100]
    return corpo


def leggi_utente_twitch(payload: object) -> tuple[str, str, str] | None:
    """(id, login, tipo di canale) dalla risposta di Twitch, o None se la forma è sbagliata."""
    try:
        voce = payload["data"][0]
        identificativo, login = str(voce["id"]), str(voce["login"])
    except (KeyError, IndexError, TypeError):
        return None
    if not identificativo.isdigit() or not (1 <= len(login) <= 40) or not login.replace("_", "").isalnum():
        return None
    return identificativo, login, tipo_canale(voce.get("broadcaster_type"))


# ----------------------------------------------------------------- token
def cifra(chiave: str, user_id: int, campo: str, valore: str | None) -> str | None:
    if valore is None:
        return None
    return oauth_crypto.encrypt_token(valore, chiave, f"alr49:{user_id}:{campo}".encode())


def decifra(chiave: str, user_id: int, campo: str, cifrato: str) -> str:
    return oauth_crypto.decrypt_token(cifrato, chiave, f"alr49:{user_id}:{campo}".encode())


def scade_tra(secondi: object) -> datetime | None:
    try:
        return datetime.now(timezone.utc) + timedelta(seconds=int(secondi))
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class TokenOAuth:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    scade_il: datetime | None = None
