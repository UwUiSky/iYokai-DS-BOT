"""
core/restore_oauth_logic.py
===============================
Logica pura del restore utenti via OAuth2: costruzione dell'URL di
autorizzazione e dello "state" firmato che lo accompagna, senza
chiamate di rete (quelle vivono in core/restore_orchestrator.py).
Funzioni coperte: SPEC §11.11 (SEC-3, SEC-19, BUG-21)

Lo state torna alla callback INVARIATO, quindi chiunque può leggerlo o
scriverne uno a mano. Per questo:
- è FIRMATO (HMAC-SHA256) con una chiave derivata (HKDF) da
  OAUTH_ENCRYPTION_KEY: senza la chiave non si costruisce uno state
  valido;
- ha una SCADENZA (STATE_TTL_SECONDS) e un NONCE: il link funziona una
  volta sola, e viene consumato solo quando il restore è riuscito;
- contiene l'ID del DESTINATARIO PREVISTO del link. Non è l'identità:
  quella si scopre solo dopo lo scambio del code, con `GET /users/@me`
  (core/restore_orchestrator.py). Lo state dice solo "per chi era" il
  link, e la callback rifiuta se chi ha autorizzato è un altro.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
OAUTH_SCOPES = "identify guilds.join"

# BUG-21: il link arriva in DM e viene aperto quando l'utente lo legge,
# anche giorni dopo — unica costante per la durata.
STATE_TTL_SECONDS = 7 * 24 * 60 * 60
_HKDF_INFO = b"iyokai-restore-state-v1"

# Nonce di link già andati a buon fine: nonce -> scadenza (per la
# pulizia lazy). In memoria: dopo un riavvio un link già usato torna
# apribile, ma solo dal suo destinatario e solo con un nuovo consenso
# su Discord, quindi al massimo rientra chi era già rientrato.
_nonces_usati: dict[str, float] = {}

# Nonce di callback in corso in questo momento: due richieste parallele
# con lo stesso link non devono procedere entrambe.
_nonces_in_corso: set[str] = set()


class RestoreStateSigningError(RuntimeError):
    """OAUTH_ENCRYPTION_KEY non configurata o non valida — senza una
    chiave non si può firmare né verificare lo state, quindi il
    restore via OAuth2 resta disattivato (stesso principio di
    OAuthEncryptionNotConfigured in core/oauth_crypto.py)."""


@dataclass(frozen=True)
class RestoreState:
    source_guild_id: int
    target_guild_id: int
    # SEC-19: a chi è stato mandato il link (non è l'identità: vedi il
    # docstring del modulo).
    user_id: int
    # Compilati da decode_and_verify_state; non contano nel confronto
    # tra due state.
    nonce: str = field(default="", compare=False)
    expires_at: float = field(default=0.0, compare=False)


def _derive_signing_key(oauth_encryption_key_b64: str) -> bytes:
    if not oauth_encryption_key_b64:
        raise RestoreStateSigningError(
            "OAUTH_ENCRYPTION_KEY non è impostata: il restore utenti via "
            "OAuth2 (SPEC.md §11.11) resta disattivato finché non viene "
            "configurata."
        )
    try:
        chiave_base = base64.urlsafe_b64decode(oauth_encryption_key_b64)
    except Exception as exc:
        raise RestoreStateSigningError("OAUTH_ENCRYPTION_KEY non è una stringa base64 valida.") from exc

    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO)
    return hkdf.derive(chiave_base)


def _pulisci_nonce_scaduti(ora: float) -> None:
    scaduti = [nonce for nonce, scadenza in _nonces_usati.items() if scadenza <= ora]
    for nonce in scaduti:
        del _nonces_usati[nonce]


def riserva_nonce(state: RestoreState, *, now: float | None = None) -> bool:
    """
    Prenota il link per la callback che lo sta elaborando. False se il
    link è già andato a buon fine o se un'altra callback lo sta usando
    in questo momento. Chi riceve True DEVE poi chiamare rilascia_nonce.
    """
    _pulisci_nonce_scaduti(now if now is not None else time.time())
    if state.nonce in _nonces_usati or state.nonce in _nonces_in_corso:
        return False
    _nonces_in_corso.add(state.nonce)
    return True


def rilascia_nonce(state: RestoreState, *, consumato: bool) -> None:
    """
    Chiude la prenotazione fatta da riserva_nonce. `consumato=True`
    solo se il restore è riuscito: da quel momento il link non funziona
    più. Con False (errore temporaneo, account sbagliato) il link resta
    utilizzabile (BUG-21).
    """
    _nonces_in_corso.discard(state.nonce)
    if consumato:
        _nonces_usati[state.nonce] = state.expires_at


def encode_state(state: RestoreState, signing_key_b64: str, *, now: float | None = None) -> str:
    """
    `base64(payload_json) + "." + HMAC-SHA256(payload_json)`. Il
    payload contiene origine, destinazione, destinatario previsto,
    scadenza e un nonce nuovo a ogni chiamata.
    """
    ora = now if now is not None else time.time()
    nonce = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")
    payload = {
        "source_guild_id": state.source_guild_id,
        "target_guild_id": state.target_guild_id,
        "user_id": state.user_id,
        "expires_at": ora + STATE_TTL_SECONDS,
        "nonce": nonce,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii")

    chiave = _derive_signing_key(signing_key_b64)
    firma = hmac.new(chiave, payload_bytes, hashlib.sha256).hexdigest()

    return f"{payload_b64}.{firma}"


def decode_and_verify_state(
    raw: str, signing_key_b64: str, *, now: float | None = None
) -> RestoreState | None:
    """
    None se lo state è malformato, la firma non torna o è scaduto — un
    callback con uno state così va trattato come non valido, mai
    sollevare un'eccezione: potrebbe essere un tentativo di
    manomissione o semplicemente un link vecchio. Verificare NON
    consuma il link: l'uso singolo passa da riserva_nonce e
    rilascia_nonce.
    """
    if "." not in raw:
        return None
    payload_b64, _, firma_ricevuta = raw.partition(".")

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
    except Exception:
        return None

    try:
        chiave = _derive_signing_key(signing_key_b64)
    except RestoreStateSigningError:
        return None

    firma_attesa = hmac.new(chiave, payload_bytes, hashlib.sha256).hexdigest()
    # Confronto su bytes: su str, compare_digest solleva TypeError se
    # la firma ricevuta contiene caratteri non ASCII (era un HTTP 500).
    if not hmac.compare_digest(firma_attesa.encode(), firma_ricevuta.encode()):
        return None

    try:
        payload = json.loads(payload_bytes)
        source_guild_id = int(payload["source_guild_id"])
        target_guild_id = int(payload["target_guild_id"])
        user_id = int(payload["user_id"])
        expires_at = float(payload["expires_at"])
        nonce = str(payload["nonce"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    ora = now if now is not None else time.time()
    if expires_at <= ora:
        return None

    return RestoreState(
        source_guild_id=source_guild_id,
        target_guild_id=target_guild_id,
        user_id=user_id,
        nonce=nonce,
        expires_at=expires_at,
    )


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    source_guild_id: int,
    target_guild_id: int,
    user_id: int,
    signing_key_b64: str,
) -> str:
    """
    URL da mandare in DM all'utente `user_id` da ripristinare —
    cliccandolo, autorizza iYokai a: leggere la sua identità
    (`identify`) e aggiungerlo a un server (`guilds.join`, richiede che
    iYokai Main abbia i permessi di gestione membri nel server di
    destinazione). Il link funziona solo per quell'utente (SEC-19).
    """
    state = encode_state(
        RestoreState(
            source_guild_id=source_guild_id, target_guild_id=target_guild_id, user_id=user_id
        ),
        signing_key_b64,
    )
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": OAUTH_SCOPES,
            "state": state,
        }
    )
    return f"{DISCORD_AUTHORIZE_URL}?{query}"
