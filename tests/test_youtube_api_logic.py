"""
tests/test_youtube_api_logic.py
===================================
Test di core/youtube_api_logic.py — logica pura, nessuna rete.
"""



class TestVideosList:
    def test_id_dalla_voce_del_feed(self):
        from core.youtube_api_logic import video_id_da_voce

        assert video_id_da_voce("yt:video:abc123") == "abc123"
        assert video_id_da_voce("altro", "https://www.youtube.com/watch?v=xyz&t=1") == "xyz"
        assert video_id_da_voce("altro", "https://esempio.com/") is None

    def test_live_solo_se_liveBroadcastContent_e_live(self):
        from core.youtube_api_logic import parse_videos_list_response, stato_live_del_canale

        info = parse_videos_list_response(
            {
                "items": [
                    {"id": "a", "snippet": {"title": "A", "liveBroadcastContent": "none"}},
                    {"id": "b", "snippet": {"title": "B", "liveBroadcastContent": "upcoming"}},
                    {"id": "c", "snippet": {"title": "C", "liveBroadcastContent": "live"}},
                    {"snippet": {}},
                ]
            }
        )
        assert stato_live_del_canale("UC", ["a", "b"], info).is_live is False
        stato = stato_live_del_canale("UC", ["a", "c"], info)
        assert stato.is_live and stato.video_id == "c" and stato.title == "C"
