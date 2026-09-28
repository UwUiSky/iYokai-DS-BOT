"""
tests/test_restore_oauth_logic.py
=====================================
Test di core/restore_oauth_logic.py — logica pura, nessuna rete.
SEC-3: state firmato, con scadenza e nonce monouso.
"""

from urllib.parse import parse_qs, urlparse

from core.oauth_crypto import generate_key
from core.restore_oauth_logic import (
    RestoreState,
    RestoreStateSigningError,
    STATE_TTL_SECONDS,
    build_authorize_url,
    decode_and_verify_state,
    encode_state,
)

CHIAVE = generate_key()


def test_encode_e_decode_state_sono_inversi():
    stato = RestoreState(source_guild_id=100, target_guild_id=200)
    assert decode_and_verify_state(encode_state(stato, CHIAVE), CHIAVE) == stato


def test_decode_state_malformato_restituisce_none():
    assert decode_and_verify_state("qualcosa-senza-punto", CHIAVE) is None
    assert decode_and_verify_state("", CHIAVE) is None
    assert decode_and_verify_state("abc.def", CHIAVE) is None


def test_decode_state_con_firma_sbagliata_restituisce_none():
    stato = RestoreState(source_guild_id=1, target_guild_id=2)
    manomesso = encode_state(stato, CHIAVE)
    payload_b64, _, _firma = manomesso.partition(".")
    manomesso_firma_finta = f"{payload_b64}.{'0' * 64}"

    assert decode_and_verify_state(manomesso_firma_finta, CHIAVE) is None


def test_decode_state_con_chiave_diversa_restituisce_none():
    stato = RestoreState(source_guild_id=1, target_guild_id=2)
    firmato = encode_state(stato, CHIAVE)

    assert decode_and_verify_state(firmato, generate_key()) is None


def test_decode_state_scaduto_restituisce_none():
    stato = RestoreState(source_guild_id=1, target_guild_id=2)
    ora = 1_000_000.0
    firmato = encode_state(stato, CHIAVE, now=ora)

    # Un secondo dopo la scadenza (TTL 10 minuti) — ancora valido un
    # secondo prima, non valido un secondo dopo: nessun off-by-one.
    assert decode_and_verify_state(firmato, CHIAVE, now=ora + STATE_TTL_SECONDS - 1) is not None
    assert decode_and_verify_state(firmato, CHIAVE, now=ora + STATE_TTL_SECONDS + 1) is None


def test_decode_state_riusato_la_seconda_volta_restituisce_none():
    """Il nonce è monouso: lo stesso link cliccato due volte funziona solo la prima."""
    stato = RestoreState(source_guild_id=1, target_guild_id=2)
    firmato = encode_state(stato, CHIAVE)

    assert decode_and_verify_state(firmato, CHIAVE) == stato
    assert decode_and_verify_state(firmato, CHIAVE) is None


def test_encode_state_senza_chiave_solleva_errore_di_configurazione():
    stato = RestoreState(source_guild_id=1, target_guild_id=2)
    try:
        encode_state(stato, "")
        assert False, "doveva sollevare RestoreStateSigningError"
    except RestoreStateSigningError:
        pass


def test_build_authorize_url_contiene_i_parametri_giusti():
    url = build_authorize_url(
        client_id="123456",
        redirect_uri="https://esempio.com/oauth/callback",
        source_guild_id=100,
        target_guild_id=200,
        signing_key_b64=CHIAVE,
    )
    assert url.startswith("https://discord.com/oauth2/authorize?")
    assert "client_id=123456" in url
    assert "response_type=code" in url
    assert "guilds.join" in url
    query = parse_qs(urlparse(url).query)
    assert "state" in query
    # Niente user_id nello state, per costruzione: due chiamate per
    # utenti diversi con la stessa coppia origine/destinazione
    # producono comunque uno state valido, mai personalizzato per ID.
    stato = decode_and_verify_state(query["state"][0], CHIAVE)
    assert stato == RestoreState(source_guild_id=100, target_guild_id=200)


def test_build_authorize_url_lo_state_e_decodificabile():
    url = build_authorize_url(
        client_id="1",
        redirect_uri="https://esempio.com/cb",
        source_guild_id=42,
        target_guild_id=43,
        signing_key_b64=CHIAVE,
    )
    query = parse_qs(urlparse(url).query)
    stato = decode_and_verify_state(query["state"][0], CHIAVE)
    assert stato == RestoreState(source_guild_id=42, target_guild_id=43)
