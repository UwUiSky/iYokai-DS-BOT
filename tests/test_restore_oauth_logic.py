"""
tests/test_restore_oauth_logic.py
=====================================
Test di core/restore_oauth_logic.py — logica pura, nessuna rete.
SEC-3/SEC-19/BUG-21: state firmato, legato al destinatario, valido 7
giorni, con nonce prenotato durante la callback e consumato solo a
restore riuscito.
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
    rilascia_nonce,
    riserva_nonce,
)

CHIAVE = generate_key()


def test_encode_e_decode_state_sono_inversi():
    stato = RestoreState(source_guild_id=100, target_guild_id=200, user_id=42)
    assert decode_and_verify_state(encode_state(stato, CHIAVE), CHIAVE) == stato


def test_decode_state_malformato_restituisce_none():
    assert decode_and_verify_state("qualcosa-senza-punto", CHIAVE) is None
    assert decode_and_verify_state("", CHIAVE) is None
    assert decode_and_verify_state("abc.def", CHIAVE) is None


def test_decode_state_con_firma_sbagliata_restituisce_none():
    stato = RestoreState(source_guild_id=1, target_guild_id=2, user_id=42)
    manomesso = encode_state(stato, CHIAVE)
    payload_b64, _, _firma = manomesso.partition(".")
    manomesso_firma_finta = f"{payload_b64}.{'0' * 64}"

    assert decode_and_verify_state(manomesso_firma_finta, CHIAVE) is None


def test_decode_state_con_chiave_diversa_restituisce_none():
    stato = RestoreState(source_guild_id=1, target_guild_id=2, user_id=42)
    firmato = encode_state(stato, CHIAVE)

    assert decode_and_verify_state(firmato, generate_key()) is None


def test_decode_state_scaduto_restituisce_none():
    stato = RestoreState(source_guild_id=1, target_guild_id=2, user_id=42)
    ora = 1_000_000.0
    firmato = encode_state(stato, CHIAVE, now=ora)

    # Ancora valido un secondo prima della scadenza, non valido un
    # secondo dopo: nessun off-by-one.
    assert decode_and_verify_state(firmato, CHIAVE, now=ora + STATE_TTL_SECONDS - 1) is not None
    assert decode_and_verify_state(firmato, CHIAVE, now=ora + STATE_TTL_SECONDS + 1) is None


def test_il_link_mandato_in_dm_vale_sette_giorni():
    """BUG-21: 10 minuti non bastano per un link che arriva in DM."""
    stato = RestoreState(source_guild_id=1, target_guild_id=2, user_id=42)
    ora = 1_000_000.0
    firmato = encode_state(stato, CHIAVE, now=ora)

    sei_giorni = 6 * 24 * 60 * 60
    otto_giorni = 8 * 24 * 60 * 60
    assert decode_and_verify_state(firmato, CHIAVE, now=ora + sei_giorni) == stato
    assert decode_and_verify_state(firmato, CHIAVE, now=ora + otto_giorni) is None


def test_decode_state_con_firma_non_ascii_restituisce_none():
    """BUG-21: una firma con caratteri non ASCII è solo un link non valido, non un errore."""
    firmato = encode_state(RestoreState(source_guild_id=1, target_guild_id=2, user_id=42), CHIAVE)
    payload_b64, _, _firma = firmato.partition(".")

    assert decode_and_verify_state(f"{payload_b64}.firma-è-finta", CHIAVE) is None


def test_decode_state_da_solo_non_consuma_il_link():
    """BUG-21: verificare lo state non lo brucia — lo fa solo un restore riuscito."""
    stato = RestoreState(source_guild_id=1, target_guild_id=2, user_id=42)
    firmato = encode_state(stato, CHIAVE)

    assert decode_and_verify_state(firmato, CHIAVE) == stato
    assert decode_and_verify_state(firmato, CHIAVE) == stato


def _state_verificato() -> RestoreState:
    stato = RestoreState(source_guild_id=1, target_guild_id=2, user_id=42)
    return decode_and_verify_state(encode_state(stato, CHIAVE), CHIAVE)


def test_nonce_prenotato_non_si_puo_prenotare_una_seconda_volta():
    """Due callback in parallelo con lo stesso link: passa solo la prima."""
    stato = _state_verificato()

    assert riserva_nonce(stato) is True
    assert riserva_nonce(stato) is False


def test_nonce_rilasciato_senza_consumo_resta_utilizzabile():
    """Un errore temporaneo non brucia il link."""
    stato = _state_verificato()

    assert riserva_nonce(stato) is True
    rilascia_nonce(stato, consumato=False)

    assert riserva_nonce(stato) is True


def test_nonce_consumato_non_e_piu_utilizzabile():
    """Dopo un restore riuscito lo stesso link non funziona più."""
    stato = _state_verificato()

    assert riserva_nonce(stato) is True
    rilascia_nonce(stato, consumato=True)

    assert riserva_nonce(stato) is False


def test_encode_state_senza_chiave_solleva_errore_di_configurazione():
    stato = RestoreState(source_guild_id=1, target_guild_id=2, user_id=42)
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
        user_id=42,
        signing_key_b64=CHIAVE,
    )
    assert url.startswith("https://discord.com/oauth2/authorize?")
    assert "client_id=123456" in url
    assert "response_type=code" in url
    assert "guilds.join" in url
    query = parse_qs(urlparse(url).query)
    assert "state" in query
    # SEC-19: lo state dice a chi era destinato il link (l'identità
    # vera resta quella che Discord conferma dopo lo scambio del code).
    stato = decode_and_verify_state(query["state"][0], CHIAVE)
    assert stato == RestoreState(source_guild_id=100, target_guild_id=200, user_id=42)


def test_build_authorize_url_lo_state_e_decodificabile():
    url = build_authorize_url(
        client_id="1",
        redirect_uri="https://esempio.com/cb",
        source_guild_id=42,
        target_guild_id=43,
        user_id=7,
        signing_key_b64=CHIAVE,
    )
    query = parse_qs(urlparse(url).query)
    stato = decode_and_verify_state(query["state"][0], CHIAVE)
    assert stato == RestoreState(source_guild_id=42, target_guild_id=43, user_id=7)
