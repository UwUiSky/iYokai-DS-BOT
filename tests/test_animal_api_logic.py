"""
tests/test_animal_api_logic.py
====================================
Test di core/animal_api_logic.py — payload finti che imitano le tre
API reali, nessuna rete coinvolta.
"""

from core.animal_api_logic import parse_cat_response, parse_dog_response, parse_fox_response


class TestParseDogResponse:
    def test_payload_valido_restituisce_url(self):
        payload = {"status": "success", "message": "https://images.dog.ceo/breeds/x/y.jpg"}
        assert parse_dog_response(payload) == "https://images.dog.ceo/breeds/x/y.jpg"

    def test_status_diverso_da_success_restituisce_none(self):
        assert parse_dog_response({"status": "error", "message": "..."}) is None

    def test_payload_non_dizionario_restituisce_none(self):
        assert parse_dog_response(["non", "un", "dizionario"]) is None

    def test_message_mancante_restituisce_none(self):
        assert parse_dog_response({"status": "success"}) is None


class TestParseCatResponse:
    def test_payload_valido_restituisce_url_del_primo_elemento(self):
        payload = [{"id": "abc", "url": "https://cdn2.thecatapi.com/x.jpg", "width": 100}]
        assert parse_cat_response(payload) == "https://cdn2.thecatapi.com/x.jpg"

    def test_lista_vuota_restituisce_none(self):
        assert parse_cat_response([]) is None

    def test_payload_non_lista_restituisce_none(self):
        assert parse_cat_response({"non": "una lista"}) is None

    def test_primo_elemento_senza_url_restituisce_none(self):
        assert parse_cat_response([{"id": "abc"}]) is None


class TestParseFoxResponse:
    def test_payload_valido_restituisce_url(self):
        payload = {"image": "https://randomfox.ca/images/x.jpg", "link": "https://randomfox.ca/?i=1"}
        assert parse_fox_response(payload) == "https://randomfox.ca/images/x.jpg"

    def test_image_mancante_restituisce_none(self):
        assert parse_fox_response({"link": "https://randomfox.ca/?i=1"}) is None

    def test_payload_non_dizionario_restituisce_none(self):
        assert parse_fox_response(None) is None
