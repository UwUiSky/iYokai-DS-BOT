"""
tests/test_chiave_soccorso_sic021.py
====================================
SIC-021 (D121): chiave di soccorso dell'owner. Il codice si mostra una volta, nel database resta solo l'impronta;
la verifica è a mano (script sul server), con un tetto ai tentativi sbagliati. Database vero.
"""

import pytest

from core import chiave_soccorso as ks
from core.database import db


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    yield


async def test_il_codice_non_e_nel_database():
    codice = await ks.crea()
    riga = await db.pool.fetchrow("SELECT * FROM owner_chiave_soccorso")
    tutto = " ".join(str(v) for v in riga.values())
    assert codice.replace("-", "") not in tutto.replace("-", "")
    assert len(codice.replace("-", "")) >= 32


async def test_verifica_giusta_e_sbagliata():
    codice = await ks.crea()
    assert await ks.verifica("SBAGLIATO") is False
    assert await ks.verifica(codice.lower().replace("-", " ")) is True  # trascritto a mano: maiuscole e trattini non contano


async def test_dopo_5_errori_si_blocca_anche_con_il_codice_giusto():
    codice = await ks.crea()
    for _ in range(ks.MAX_ERRORI):
        assert await ks.verifica("no") is False
    assert await ks.verifica(codice) is False
    assert (await ks.stato()).bloccata is True


async def test_crea_sostituisce_solo_se_richiesto():
    primo = await ks.crea()
    with pytest.raises(ks.GiaPresente):
        await ks.crea()
    secondo = await ks.crea(sostituisci=True)
    assert primo != secondo
    assert await ks.verifica(primo) is False
    assert await ks.verifica(secondo) is True


async def test_stato_e_revoca():
    assert (await ks.stato()).presente is False
    await ks.crea()
    assert (await ks.stato()).presente is True
    assert await ks.revoca() is True
    assert await ks.revoca() is False


async def test_una_verifica_riuscita_si_segna():
    codice = await ks.crea()
    await ks.verifica(codice)
    assert (await ks.stato()).ultimo_uso is not None
