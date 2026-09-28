"""
core/restore_oauth_logic.py
===============================
Logica pura del restore utenti via OAuth2 (SPEC.md §11.11) — costruzione
dell'URL di autorizzazione e dello "state" firmato che lo accompagna,
senza alcuna chiamata di rete: quella vive in core/restore_orchestrator.py.

SEC-3 (issue #8): lo "state" OAuth2 torna alla callback INVARIATO —
Discord lo rimanda così com'è insieme al `code` — quindi chiunque può
leggerlo o costruirsene uno a mano. Per questo:
- è FIRMATO (HMAC-SHA256): senza la chiave giusta non si può
  costruire uno state che superi la verifica;
- ha una SCADENZA (10 minuti) e un NONCE monouso tracciato in memoria:
  un link vecchio o già usato viene rifiutato, non solo uno manomesso;
- NON contiene `user_id`: prima lo conteneva in chiaro, quindi
  chiunque poteva scrivere l'ID di un altro utente e — passando dallo
  scambio del `code`, comunque necessario — sovrascrivergli il token
  salvato o azzerargli lo stato di blacklist. L'identità vera si
  scopre SOLO dopo lo scambio del code, chiamando `GET /users/@me`
  con l'access_token appena ottenuto (core/restore_orchestrator.py:
  fetch_current_user) — l'unica fonte affidabile, perché richiede che
  la PERSONA abbia effettivamente autorizzato con il proprio account.

La chiave di firma non è una nuova variabile da configurare: si
deriva con HKDF dalla chiave di cifratura dei token già esistente
(OAUTH_ENCRYPTION_KEY, core/oauth_crypto.py) — mai la stessa chiave
riusata per due scopi diversi, quindi non cifra/firma nulla
direttamente, serve solo come materiale per derivarne una seconda.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
OAUTH_SCOPES = "identify guilds.join"

STATE_TTL_SECONDS = 10 * 60
_HKDF_INFO = b"iyokai-restore-state-v1"

# Nonce già consumati: nonce -> scadenza (per la pulizia lazy). In
# memoria è sufficiente — uno state vive al massimo 10 minuti, e un
# riavvio del bot lo invalida comunque (serve un click fresco sul
# pannello di verifica/DM per ottenerne uno nuovo).
_nonces_usati: dict[str, float] = {}


class RestoreStateSigningError(RuntimeError):
    """OAUTH_ENCRYPTION_KEY non configurata o non valida — senza una
    chiave non si può firmare né verificare lo state, quindi il
    restore via OAuth2 resta disattivato (stesso principio di
    OAuthEncryptionNotConfigured in core/oauth_crypto.py)."""


@dataclass(frozen=True)
class RestoreState:
    source_guild_id: int
    target_guild_id: int


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


def encode_state(state: RestoreState, signing_key_b64: str, *, now: float | None = None) -> str:
    """
    `base64(payload_json) + "." + HMAC-SHA256(payload_json)`. Il
    payload contiene origine, destinazione, scadenza e un nonce
    monouso — mai lo user_id, vedi il docstring del modulo.
    """
    ora = now if now is not None else time.time()
    nonce = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")
    payload = {
        "source_guild_id": state.source_guild_id,
        "target_guild_id": state.target_guild_id,
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
    None se lo state è malformato, la firma non torna, è scaduto o il
    nonce è già stato usato — un callback con uno state così va
    trattato come non valido, mai sollevare un'eccezione: potrebbe
    essere un tentativo di manomissione o semplicemente un link
    vecchio ricliccato due volte.
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
    if not hmac.compare_digest(firma_attesa, firma_ricevuta):
        return None

    try:
        payload = json.loads(payload_bytes)
        source_guild_id = int(payload["source_guild_id"])
        target_guild_id = int(payload["target_guild_id"])
        expires_at = float(payload["expires_at"])
        nonce = str(payload["nonce"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    ora = now if now is not None else time.time()
    if expires_at <= ora:
        return None

    _pulisci_nonce_scaduti(ora)
    if nonce in _nonces_usati:
        return None
    _nonces_usati[nonce] = expires_at

    return RestoreState(source_guild_id=source_guild_id, target_guild_id=target_guild_id)


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    source_guild_id: int,
    target_guild_id: int,
    signing_key_b64: str,
) -> str:
    """
    URL da mandare in DM all'utente da ripristinare — cliccandolo,
    autorizza iYokai a: leggere la sua identità (`identify`) e
    aggiungerlo a un server (`guilds.join`, richiede che iYokai Main
    abbia i permessi di gestione membri nel server di destinazione).
    """
    state = encode_state(
        RestoreState(source_guild_id=source_guild_id, target_guild_id=target_guild_id),
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
