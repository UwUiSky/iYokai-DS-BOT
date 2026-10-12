"""
core/oauth_crypto.py
========================
Cifratura a riposo dei token OAuth2 altrui salvati per il restore
massivo utenti (SPEC.md §11.11). Algoritmo standard e verificato
pubblicamente — **deliberatamente NON un algoritmo "custom"**: un
algoritmo inventato in casa, senza revisione pubblica, è quasi
sempre PIÙ debole di uno standard, non più sicuro — "nessuno lo
conosce" non è una proprietà crittografica, è solo un ritardo prima
che qualcuno lo rompa. La vera protezione sta nella CHIAVE (segreta,
mai nel DB, letta da OAUTH_ENCRYPTION_KEY), non nell'oscurità
dell'algoritmo.

AES-256-GCM (AEAD — cifra E autentica in un solo passaggio: se il
testo cifrato viene alterato, decrypt() solleva invece di restituire
dati corrotti silenziosamente). Un nonce casuale a 12 byte per ogni
cifratura viene anteposto al testo cifrato; il tutto sta in un solo
campo TEXT con un prefisso di versione e l'identificativo della chiave.
Funzioni coperte: SPEC §11.11, M 12.15
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_LENGTH_BYTES = 12
PREFISSO_V2 = "v2"


class OAuthEncryptionNotConfigured(RuntimeError):
    """OAUTH_ENCRYPTION_KEY non impostata — il modulo restore via
    OAuth2 resta disattivato finché l'utente non la configura,
    invece di salvare token in chiaro o con una chiave finta."""


def _decodifica_chiave(raw_key: str) -> bytes:
    try:
        chiave = base64.urlsafe_b64decode(raw_key.strip())
    except Exception as exc:
        raise OAuthEncryptionNotConfigured(
            "OAUTH_ENCRYPTION_KEY non è una stringa base64 valida."
        ) from exc

    if len(chiave) != 32:
        raise OAuthEncryptionNotConfigured(
            f"OAUTH_ENCRYPTION_KEY deve decodificare a 32 byte esatti "
            f"(AES-256), trovati {len(chiave)}."
        )
    return chiave


def _carica_chiavi(raw_key: str) -> list[bytes]:
    """
    M 12.15 (LIM-52): ``raw_key`` può contenere più chiavi separate da virgola,
    la più nuova per prima. Si scrive con la prima, si legge con tutte: per
    ruotare la chiave basta anteporre quella nuova e tenere la vecchia finché
    nessun dato la usa più.
    """
    if not raw_key:
        raise OAuthEncryptionNotConfigured(
            "OAUTH_ENCRYPTION_KEY non è impostata: il restore utenti via "
            "OAuth2 (SPEC.md §11.11) resta disattivato finché non viene "
            "configurata una chiave di cifratura."
        )
    parti = [p for p in raw_key.split(",") if p.strip()]
    if not parti:
        raise OAuthEncryptionNotConfigured("OAUTH_ENCRYPTION_KEY è vuota.")
    return [_decodifica_chiave(p) for p in parti]


def _id_chiave(chiave: bytes) -> str:
    return hashlib.sha256(chiave).hexdigest()[:8]


def encrypt_token(plaintext: str, raw_key: str, aad: bytes | None = None) -> str:
    """
    Cifra una stringa (un access_token o refresh_token). Formato
    ``v2.<id chiave>.<base64 di nonce + testo cifrato>``. ``aad`` è il dato
    associato (ID di server e utente): un cifrato copiato su un'altra riga
    non si decifra più (SEC-16).
    """
    chiave = _carica_chiavi(raw_key)[0]
    nonce = os.urandom(NONCE_LENGTH_BYTES)
    ciphertext = AESGCM(chiave).encrypt(nonce, plaintext.encode("utf-8"), associated_data=aad)
    corpo = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"{PREFISSO_V2}.{_id_chiave(chiave)}.{corpo}"


def decrypt_token(encrypted: str, raw_key: str, aad: bytes | None = None) -> str:
    """
    Inverso di encrypt_token(). Solleva cryptography.exceptions.InvalidTag
    se il cifrato è alterato, la chiave non c'è o ``aad`` non corrisponde:
    MAI dati corrotti in silenzio. Il formato precedente (senza prefisso e
    senza dato associato) resta leggibile e si riscrive al primo aggiornamento.
    """
    chiavi = _carica_chiavi(raw_key)
    if encrypted.startswith(f"{PREFISSO_V2}."):
        _, id_chiave, corpo = encrypted.split(".", 2)
        chiave = next((k for k in chiavi if _id_chiave(k) == id_chiave), None)
        if chiave is None:
            raise InvalidTag()
        dati = base64.urlsafe_b64decode(corpo)
        nonce, ciphertext = dati[:NONCE_LENGTH_BYTES], dati[NONCE_LENGTH_BYTES:]
        return AESGCM(chiave).decrypt(nonce, ciphertext, associated_data=aad).decode("utf-8")

    dati = base64.urlsafe_b64decode(encrypted)
    nonce, ciphertext = dati[:NONCE_LENGTH_BYTES], dati[NONCE_LENGTH_BYTES:]
    for chiave in chiavi:
        try:
            return AESGCM(chiave).decrypt(nonce, ciphertext, associated_data=None).decode("utf-8")
        except InvalidTag:
            continue
    raise InvalidTag()


def generate_key() -> str:
    """Genera una nuova chiave valida (32 byte casuali, base64) — usata
    dallo script di setup/CLI, non a runtime dal bot."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
