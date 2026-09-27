"""
tests/test_image_search_logic.py
======================================
Test di core/image_search_logic.py — payload finto che imita la
risposta reale di Pixabay, nessuna rete coinvolta.
"""

from core.image_search_logic import parse_pixabay_response


class TestParsePixabayResponse:
    def test_payload_valido_restituisce_lista_di_url(self):
        payload = {
            "total": 2,
            "totalHits": 2,
            "hits": [
                {"webformatURL": "https://pixabay.com/a.jpg", "tags": "gatto, animale"},
                {"webformatURL": "https://pixabay.com/b.jpg", "tags": "cane, animale"},
            ],
        }
        assert parse_pixabay_response(payload) == [
            "https://pixabay.com/a.jpg",
            "https://pixabay.com/b.jpg",
        ]

    def test_nessun_risultato_restituisce_lista_vuota(self):
        assert parse_pixabay_response({"total": 0, "totalHits": 0, "hits": []}) == []

    def test_payload_non_dizionario_restituisce_lista_vuota(self):
        assert parse_pixabay_response(["non", "un", "dizionario"]) == []

    def test_hits_mancante_restituisce_lista_vuota(self):
        assert parse_pixabay_response({"total": 0}) == []

    def test_elemento_senza_url_viene_saltato(self):
        payload = {"hits": [{"tags": "senza url"}, {"webformatURL": "https://pixabay.com/c.jpg"}]}
        assert parse_pixabay_response(payload) == ["https://pixabay.com/c.jpg"]
