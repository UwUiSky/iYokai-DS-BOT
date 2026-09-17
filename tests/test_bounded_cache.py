"""
tests/test_bounded_cache.py
==============================
Test di core/bounded_cache.py. Logica pura, nessuna dipendenza
esterna. Il punto più importante da verificare è che un GET conti
come "uso recente" (non solo un SET) — altrimenti la cache
espellerebbe elementi letti spesso ma scritti una volta sola,
comportamento sbagliato per una vera LRU.
"""

import pytest

from core.bounded_cache import BoundedCache


class TestCostruzione:
    def test_max_size_zero_solleva_errore(self):
        with pytest.raises(ValueError):
            BoundedCache(max_size=0)

    def test_max_size_negativo_solleva_errore(self):
        with pytest.raises(ValueError):
            BoundedCache(max_size=-1)

    def test_cache_vuota_ha_lunghezza_zero(self):
        cache = BoundedCache(max_size=10)
        assert len(cache) == 0


class TestOperazioniBase:
    def test_set_e_get(self):
        cache = BoundedCache(max_size=10)
        cache.set("a", 1)
        assert cache.get("a") == 1

    def test_get_chiave_assente_restituisce_none(self):
        cache = BoundedCache(max_size=10)
        assert cache.get("assente") is None

    def test_get_chiave_assente_con_default(self):
        cache = BoundedCache(max_size=10)
        assert cache.get("assente", default="valore_default") == "valore_default"

    def test_contains(self):
        cache = BoundedCache(max_size=10)
        cache.set("a", 1)
        assert "a" in cache
        assert "b" not in cache

    def test_delete(self):
        cache = BoundedCache(max_size=10)
        cache.set("a", 1)
        cache.delete("a")
        assert "a" not in cache

    def test_delete_chiave_assente_non_fallisce(self):
        cache = BoundedCache(max_size=10)
        cache.delete("assente")  # non deve sollevare eccezioni

    def test_clear(self):
        cache = BoundedCache(max_size=10)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0

    def test_set_sovrascrive_valore_esistente(self):
        cache = BoundedCache(max_size=10)
        cache.set("a", 1)
        cache.set("a", 2)
        assert cache.get("a") == 2
        assert len(cache) == 1  # non è un elemento nuovo, sovrascrive


class TestPoliticaLRU:
    def test_oltre_la_dimensione_massima_espelle_il_meno_usato(self):
        cache = BoundedCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # supera il limite: "a" va espulso

        assert "a" not in cache
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert len(cache) == 2

    def test_un_get_conta_come_uso_recente(self):
        # Il caso che distingue una vera LRU da un semplice FIFO:
        # "a" viene LETTO (non solo scritto) prima che "c" causi
        # un'espulsione — deve sopravvivere al posto di "b", che
        # non è stato toccato da quando è stato inserito.
        cache = BoundedCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # "a" torna ad essere il più recente
        cache.set("c", 3)  # ora "b" è il meno usato, non "a"

        assert "a" in cache
        assert "b" not in cache
        assert "c" in cache

    def test_un_set_su_chiave_esistente_conta_come_uso_recente(self):
        cache = BoundedCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("a", 10)  # riscrittura: "a" torna il più recente
        cache.set("c", 3)  # "b" è il meno usato

        assert "a" in cache
        assert "b" not in cache

    def test_espulsioni_multiple_in_sequenza(self):
        cache = BoundedCache(max_size=3)
        for i in range(10):
            cache.set(f"chiave{i}", i)

        # Devono restare solo le ultime 3 chiavi inserite.
        assert len(cache) == 3
        assert set(cache.keys()) == {"chiave7", "chiave8", "chiave9"}

    def test_max_size_uno(self):
        cache = BoundedCache(max_size=1)
        cache.set("a", 1)
        cache.set("b", 2)
        assert "a" not in cache
        assert cache.get("b") == 2
        assert len(cache) == 1


class TestKeys:
    def test_keys_restituisce_tutte_le_chiavi_presenti(self):
        cache = BoundedCache(max_size=10)
        cache.set("a", 1)
        cache.set("b", 2)
        assert set(cache.keys()) == {"a", "b"}

    def test_keys_su_cache_vuota(self):
        cache = BoundedCache(max_size=10)
        assert cache.keys() == []


def test_max_size_property():
    cache = BoundedCache(max_size=42)
    assert cache.max_size == 42
