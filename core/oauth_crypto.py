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
dati corrotti silenziosamente, importante per un token di accesso a
un account Discord altrui). Un nonce casuale a 12 byte per ogni
cifratura (mai riutilizzato con la stessa chiave, requisito di
sicurezza di GCM) viene anteposto al testo cifrato — non serve
segreto, solo univoco, ed è più semplice da salvare tutto in un solo
campo TEXT nel DB (base64 di nonce+ciphertext) piuttosto che due
colonne separate.
"""

# DA FARE (issue #68, fase F3): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §12 (Backup e restore).

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_LENGTH_BYTES = 12


class OAuthEncryptionNotConfigured(RuntimeError):
    """OAUTH_ENCRYPTION_KEY non impostata — il modulo restore via
    OAuth2 resta disattivato finché l'utente non la configura,
    invece di salvare token in chiaro o con una chiave finta."""


def _load_key(raw_key: str) -> bytes:
    if not raw_key:
        raise OAuthEncryptionNotConfigured(
            "OAUTH_ENCRYPTION_KEY non è impostata: il restore utenti via "
            "OAuth2 (SPEC.md §11.11) resta disattivato finché non viene "
            "configurata una chiave di cifratura."
        )
    try:
        chiave = base64.urlsafe_b64decode(raw_key)
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


def encrypt_token(plaintext: str, raw_key: str) -> str:
    """
    Cifra una stringa (un access_token o refresh_token) e restituisce
    una stringa base64 pronta da salvare in una colonna TEXT —
    nonce (12 byte) + ciphertext, concatenati prima della codifica.
    """
    chiave = _load_key(raw_key)
    aesgcm = AESGCM(chiave)
    nonce = os.urandom(NONCE_LENGTH_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_token(encrypted: str, raw_key: str) -> str:
    """
    Inverso di encrypt_token(). Solleva cryptography.exceptions.
    InvalidTag se il testo cifrato è stato alterato o la chiave non è
    quella giusta — MAI restituisce dati corrotti silenziosamente.
    """
    chiave = _load_key(raw_key)
    dati = base64.urlsafe_b64decode(encrypted)
    nonce, ciphertext = dati[:NONCE_LENGTH_BYTES], dati[NONCE_LENGTH_BYTES:]
    aesgcm = AESGCM(chiave)
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    return plaintext.decode("utf-8")


def generate_key() -> str:
    """Genera una nuova chiave valida (32 byte casuali, base64) — usata
    dallo script di setup/CLI, non a runtime dal bot."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
