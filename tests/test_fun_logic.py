"""
tests/test_fun_logic.py
==========================
Test di core/fun_logic.py — logica pura.
"""

from core.fun_logic import (
    compute_rate_score,
    compute_ship_percentage,
    rate_flavor_text,
    ship_flavor_text,
)


class TestComputeShipPercentage:
    def test_e_deterministico(self):
        assert compute_ship_percentage(100, 200) == compute_ship_percentage(100, 200)

    def test_e_simmetrico(self):
        assert compute_ship_percentage(100, 200) == compute_ship_percentage(200, 100)

    def test_restituisce_un_valore_tra_0_e_100(self):
        for a, b in [(1, 2), (999999, 1), (0, 0), (123456789, 987654321)]:
            percentuale = compute_ship_percentage(a, b)
            assert 0 <= percentuale <= 100

    def test_coppie_diverse_danno_di_solito_risultati_diversi(self):
        risultati = {compute_ship_percentage(i, i + 1) for i in range(20)}
        # Non deve essere sempre lo stesso numero per ogni coppia -
        # un bug plausibile (es. hash che ignora uno dei due ID)
        # produrrebbe un solo valore ripetuto.
        assert len(risultati) > 1

    def test_stesso_utente_con_se_stesso_e_deterministico(self):
        assert compute_ship_percentage(42, 42) == compute_ship_percentage(42, 42)


class TestShipFlavorText:
    def test_percentuale_alta_ha_testo_positivo(self):
        assert "gemelle" in ship_flavor_text(95).lower() or "💍" in ship_flavor_text(95)

    def test_percentuale_bassa_ha_testo_negativo(self):
        assert "olio" in ship_flavor_text(5).lower()

    def test_ogni_percentuale_da_0_a_100_ha_un_testo(self):
        for p in range(0, 101):
            testo = ship_flavor_text(p)
            assert isinstance(testo, str) and len(testo) > 0


class TestComputeRateScore:
    def test_e_deterministico(self):
        assert compute_rate_score("pizza") == compute_rate_score("pizza")

    def test_ignora_spazi_e_maiuscole(self):
        assert compute_rate_score("Pizza") == compute_rate_score(" pizza ")

    def test_restituisce_un_valore_tra_0_e_10(self):
        for testo in ["ciao", "un testo molto lungo" * 10, "", "123"]:
            punteggio = compute_rate_score(testo)
            assert 0 <= punteggio <= 10

    def test_testi_diversi_danno_di_solito_punteggi_diversi(self):
        risultati = {compute_rate_score(f"testo numero {i}") for i in range(20)}
        assert len(risultati) > 1


class TestRateFlavorText:
    def test_punteggio_alto_ha_testo_positivo(self):
        assert "perfezione" in rate_flavor_text(10).lower()

    def test_punteggio_basso_ha_testo_negativo(self):
        assert "disastro" in rate_flavor_text(0).lower()

    def test_ogni_punteggio_da_0_a_10_ha_un_testo(self):
        for p in range(0, 11):
            testo = rate_flavor_text(p)
            assert isinstance(testo, str) and len(testo) > 0
