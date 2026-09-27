"""
tests/test_restore_oauth_logic.py
=====================================
Test di core/restore_oauth_logic.py — logica pura, nessuna rete.
"""

from core.restore_oauth_logic import (
    RestoreState,
    build_authorize_url,
    decode_state,
    encode_state,
)


def test_encode_e_decode_state_sono_inversi():
    stato = RestoreState(source_guild_id=100, target_guild_id=200, user_id=999)
    assert decode_state(encode_state(stato)) == stato


def test_decode_state_malformato_restituisce_none():
    assert decode_state("qualcosa-senza-i-due-punti-giusti") is None
    assert decode_state("100:200") is None
    assert decode_state("100:200:abc") is None
    assert decode_state("") is None


def test_build_authorize_url_contiene_i_parametri_giusti():
    url = build_authorize_url(
        client_id="123456",
        redirect_uri="https://esempio.com/oauth/callback",
        source_guild_id=100,
        target_guild_id=200,
        user_id=999,
    )
    assert url.startswith("https://discord.com/oauth2/authorize?")
    assert "client_id=123456" in url
    assert "response_type=code" in url
    assert "guilds.join" in url
    assert "state=100%3A200%3A999" in url  # ":" url-encoded


def test_build_authorize_url_lo_state_e_decodificabile():
    url = build_authorize_url(
        client_id="1",
        redirect_uri="https://esempio.com/cb",
        source_guild_id=42,
        target_guild_id=43,
        user_id=44,
    )
    # Estrae grezzamente il parametro state dalla query string.
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(url).query)
    stato = decode_state(query["state"][0])
    assert stato == RestoreState(source_guild_id=42, target_guild_id=43, user_id=44)
