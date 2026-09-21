"""
tests/test_twitch_api_logic.py
==================================
Test di core/twitch_api_logic.py — logica pura.
"""

from core.twitch_api_logic import (
    parse_app_access_token_response,
    parse_get_streams_response,
)

RISPOSTA_GET_STREAMS_ESEMPIO = {
    "data": [
        {
            "user_login": "streamerA",
            "title": "Serata di gioco",
            "game_name": "Just Chatting",
        }
    ],
    "pagination": {},
}


class TestParseGetStreamsResponse:
    def test_streamer_presente_nella_risposta_e_live(self):
        risultati = parse_get_streams_response(
            RISPOSTA_GET_STREAMS_ESEMPIO, logins_richiesti=["streamerA"]
        )
        assert risultati[0].is_live is True
        assert risultati[0].title == "Serata di gioco"
        assert risultati[0].game_name == "Just Chatting"

    def test_streamer_assente_dalla_risposta_e_offline(self):
        risultati = parse_get_streams_response(
            RISPOSTA_GET_STREAMS_ESEMPIO, logins_richiesti=["streamerB"]
        )
        assert risultati[0].login == "streamerb"
        assert risultati[0].is_live is False
        assert risultati[0].title is None

    def test_confronto_case_insensitive(self):
        risultati = parse_get_streams_response(
            RISPOSTA_GET_STREAMS_ESEMPIO, logins_richiesti=["STREAMERA"]
        )
        assert risultati[0].is_live is True

    def test_piu_login_richiesti_mix_di_live_e_offline(self):
        risultati = parse_get_streams_response(
            RISPOSTA_GET_STREAMS_ESEMPIO, logins_richiesti=["streamerA", "streamerC"]
        )
        assert len(risultati) == 2
        assert risultati[0].is_live is True
        assert risultati[1].is_live is False

    def test_risposta_senza_dati_tutti_offline(self):
        risultati = parse_get_streams_response({"data": []}, logins_richiesti=["x", "y"])
        assert all(not r.is_live for r in risultati)

    def test_chiave_data_mancante_non_solleva(self):
        risultati = parse_get_streams_response({}, logins_richiesti=["x"])
        assert risultati[0].is_live is False


class TestParseAppAccessTokenResponse:
    def test_risposta_valida(self):
        risultato = parse_app_access_token_response(
            {"access_token": "abc123", "expires_in": 5000, "token_type": "bearer"}
        )
        assert risultato == ("abc123", 5000)

    def test_risposta_senza_token_restituisce_none(self):
        assert parse_app_access_token_response({"message": "invalid client"}) is None

    def test_risposta_senza_expires_in_restituisce_none(self):
        assert parse_app_access_token_response({"access_token": "abc123"}) is None
