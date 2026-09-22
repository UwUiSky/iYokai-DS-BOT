"""
tests/test_giveaway_logic.py
================================
Test di core/giveaway_logic.py — logica pura.
"""

import random

from core.giveaway_logic import is_eligible, pick_winners


class TestPickWinners:
    def test_estrae_il_numero_richiesto(self):
        vincitori = pick_winners([1, 2, 3, 4, 5], winners_count=2, rng=random.Random(42))
        assert len(vincitori) == 2

    def test_nessuna_ripetizione(self):
        vincitori = pick_winners([1, 2, 3], winners_count=3, rng=random.Random(1))
        assert len(set(vincitori)) == 3

    def test_meno_partecipanti_dei_vincitori_richiesti_li_vincono_tutti(self):
        vincitori = pick_winners([1, 2], winners_count=5, rng=random.Random(1))
        assert sorted(vincitori) == [1, 2]

    def test_lista_vuota_restituisce_vuota(self):
        assert pick_winners([], winners_count=3, rng=random.Random(1)) == []

    def test_deterministico_con_lo_stesso_seed(self):
        primo = pick_winners([1, 2, 3, 4, 5, 6, 7, 8], winners_count=3, rng=random.Random(7))
        secondo = pick_winners([1, 2, 3, 4, 5, 6, 7, 8], winners_count=3, rng=random.Random(7))
        assert primo == secondo


class TestIsEligible:
    def test_nessun_requisito_tutti_idonei(self):
        assert is_eligible(user_level=0, user_role_ids=set(), min_level=0, required_role_id=None) is True

    def test_livello_insufficiente_non_idoneo(self):
        assert is_eligible(user_level=5, user_role_ids=set(), min_level=10, required_role_id=None) is False

    def test_livello_sufficiente_idoneo(self):
        assert is_eligible(user_level=10, user_role_ids=set(), min_level=10, required_role_id=None) is True

    def test_manca_il_ruolo_richiesto_non_idoneo(self):
        assert is_eligible(user_level=0, user_role_ids={1, 2}, min_level=0, required_role_id=99) is False

    def test_ha_il_ruolo_richiesto_idoneo(self):
        assert is_eligible(user_level=0, user_role_ids={1, 99}, min_level=0, required_role_id=99) is True

    def test_entrambi_i_requisiti_servono_insieme(self):
        # Livello sufficiente ma ruolo mancante -> comunque non idoneo.
        assert is_eligible(user_level=20, user_role_ids=set(), min_level=10, required_role_id=99) is False
