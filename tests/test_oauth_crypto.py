"""
tests/test_oauth_crypto.py
==============================
Test di core/oauth_crypto.py — cifratura AES-256-GCM dei token OAuth
altrui (SPEC.md §11.11). Nessun I/O, nessun DB: solo cifra/decifra.
"""

import base64

import pytest
from cryptography.exceptions import InvalidTag

from core.oauth_crypto import (
    OAuthEncryptionNotConfigured,
    decrypt_token,
    encrypt_token,
    generate_key,
)

CHIAVE_VALIDA = generate_key()


def test_generate_key_produce_32_byte_decodificati():
    chiave = generate_key()
    assert len(base64.urlsafe_b64decode(chiave)) == 32


def test_cifra_e_decifra_torna_al_testo_originale():
    cifrato = encrypt_token("un-access-token-segreto", CHIAVE_VALIDA)
    assert decrypt_token(cifrato, CHIAVE_VALIDA) == "un-access-token-segreto"


def test_il_testo_cifrato_non_contiene_il_plaintext():
    cifrato = encrypt_token("token-di-prova-12345", CHIAVE_VALIDA)
    assert "token-di-prova-12345" not in cifrato


def test_due_cifrature_dello_stesso_testo_producono_output_diversi():
    # Nonce casuale ad ogni chiamata: anche stesso testo, stessa
    # chiave, output diverso — altrimenti un dump del DB rivelerebbe
    # quali utenti hanno lo stesso token.
    a = encrypt_token("stesso-token", CHIAVE_VALIDA)
    b = encrypt_token("stesso-token", CHIAVE_VALIDA)
    assert a != b


def test_decifrare_con_la_chiave_sbagliata_solleva():
    cifrato = encrypt_token("segreto", CHIAVE_VALIDA)
    with pytest.raises(InvalidTag):
        decrypt_token(cifrato, generate_key())


def test_testo_cifrato_manomesso_solleva_invece_di_corrompere_silenziosamente():
    cifrato = encrypt_token("segreto", CHIAVE_VALIDA)
    grezzo = bytearray(base64.urlsafe_b64decode(cifrato))
    grezzo[-1] ^= 0xFF  # altera un byte del ciphertext/tag
    manomesso = base64.urlsafe_b64encode(bytes(grezzo)).decode("ascii")

    with pytest.raises(InvalidTag):
        decrypt_token(manomesso, CHIAVE_VALIDA)


def test_chiave_vuota_solleva_not_configured():
    with pytest.raises(OAuthEncryptionNotConfigured):
        encrypt_token("qualcosa", "")


def test_chiave_di_lunghezza_sbagliata_solleva_not_configured():
    chiave_corta = base64.urlsafe_b64encode(b"troppo-corta").decode("ascii")
    with pytest.raises(OAuthEncryptionNotConfigured):
        encrypt_token("qualcosa", chiave_corta)


def test_chiave_non_base64_solleva_not_configured():
    with pytest.raises(OAuthEncryptionNotConfigured):
        encrypt_token("qualcosa", "questo non è base64 valido!!!")
