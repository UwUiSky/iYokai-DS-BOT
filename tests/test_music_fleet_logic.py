"""
tests/test_music_fleet_logic.py
===================================
Test di core/music_fleet_logic.py — logica pura.
"""

from core.music_fleet_logic import find_free_worker


class TestFindFreeWorker:
    def test_nessuno_occupato_restituisce_il_primo(self):
        assert find_free_worker(set()) == 1

    def test_primo_occupato_restituisce_il_secondo(self):
        assert find_free_worker({1}) == 2

    def test_ordine_di_occupazione_non_conta_solo_quale_e_libero(self):
        assert find_free_worker({2, 4}) == 1

    def test_tutti_occupati_tranne_l_ultimo(self):
        assert find_free_worker({1, 2, 3, 4}) == 5

    def test_tutti_occupati_restituisce_none(self):
        assert find_free_worker({1, 2, 3, 4, 5}) is None

    def test_occupati_fuori_range_vengono_ignorati(self):
        # Un ID di worker che non esiste più (es. dopo aver ridotto
        # il numero di istanze) non deve mai bloccare la ricerca.
        assert find_free_worker({99, 100}) == 1

    def test_rispetta_un_numero_di_worker_personalizzato(self):
        assert find_free_worker({1, 2}, total_workers=3) == 3
        assert find_free_worker({1, 2, 3}, total_workers=3) is None
