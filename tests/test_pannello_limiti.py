"""
tests/test_pannello_limiti.py
=============================
Blocco A, voce 6: i limiti del pannello che proteggono Discord e i segreti (marchio, sincronia dei permessi, copia dei
dati) contano nel database: un riavvio (un oggetto nuovo) non li azzera, e due richieste insieme non superano il tetto.
"""

import asyncio

import pytest

from core.repositories.pannello_limiti_repo import LimitePersistente


@pytest.fixture
def pool(clean_db):
    return lambda: clean_db


async def test_il_tetto_regge_anche_dopo_un_riavvio(pool):
    prima = LimitePersistente("prova", 2, 60, "server", pool)
    assert [await prima.consenti(7) for _ in range(3)] == [True, True, False]
    dopo_il_riavvio = LimitePersistente("prova", 2, 60, "server", pool)  # nuovo oggetto, stessa tabella
    assert await dopo_il_riavvio.consenti(7) is False
    assert await dopo_il_riavvio.consenti(8) is True  # un altro soggetto ha il suo conto


async def test_i_colpi_vecchi_escono_dalla_finestra(pool, clean_db):
    limite = LimitePersistente("prova", 1, 60, "utente", pool)
    assert await limite.consenti(5) is True
    await clean_db.execute("UPDATE pannello_limiti SET colpito_il = now() - interval '61 seconds'")
    assert await limite.consenti(5) is True
    assert await clean_db.fetchval("SELECT count(*) FROM pannello_limiti") == 1


async def test_richieste_insieme_ne_passa_solo_il_tetto(pool):
    limite = LimitePersistente("prova", 3, 60, "server", pool)
    esiti = await asyncio.gather(*[limite.consenti(9) for _ in range(12)])
    assert esiti.count(True) == 3


async def test_se_il_database_non_risponde_la_richiesta_non_passa():
    class _Rotto:
        def acquire(self):
            raise OSError("database spento")

    limite = LimitePersistente("prova", 3, 60, "server", lambda: _Rotto())
    assert await limite.consenti(1) is False


def test_ambito_non_valido_e_un_errore():
    with pytest.raises(ValueError):
        LimitePersistente("x", 1, 1, "altro")
