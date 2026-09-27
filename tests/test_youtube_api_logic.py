"""
tests/test_youtube_api_logic.py
===================================
Test di core/youtube_api_logic.py — logica pura, nessuna rete.
"""

from core.youtube_api_logic import parse_search_live_response


class TestParseSearchLiveResponse:
    def test_nessun_item_significa_non_live(self):
        stato = parse_search_live_response({"items": []}, channel_id="UC123")
        assert stato.is_live is False
        assert stato.channel_id == "UC123"
        assert stato.video_id is None

    def test_items_assente_significa_non_live(self):
        stato = parse_search_live_response({}, channel_id="UC123")
        assert stato.is_live is False

    def test_item_presente_significa_live(self):
        payload = {
            "items": [
                {
                    "id": {"videoId": "abc123"},
                    "snippet": {"title": "Diretta di prova"},
                }
            ]
        }
        stato = parse_search_live_response(payload, channel_id="UC123")
        assert stato.is_live is True
        assert stato.video_id == "abc123"
        assert stato.title == "Diretta di prova"

    def test_item_senza_video_id_trattato_come_non_live(self):
        payload = {"items": [{"id": {}, "snippet": {"title": "x"}}]}
        stato = parse_search_live_response(payload, channel_id="UC123")
        assert stato.is_live is False
