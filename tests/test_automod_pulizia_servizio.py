"""
tests/test_automod_pulizia_servizio.py
======================================
Impostazioni della pulizia dei canali su PostgreSQL vero (AMD-073, 074): un solo punto di scrittura, tetto per
server, prima pulizia dopo un intero intervallo, giro dovuto segnato prima di cancellare, riga tolta con il canale.
"""

import pytest

from core import automod_pulizia_logic as lg
from core import automod_pulizia_service as servizio
from core.repositories.automod_pulizie_repo import automod_pulizie_repo as repo

G = 666


@pytest.fixture(autouse=True)
def db(clean_db, monkeypatch):
    monkeypatch.setattr(repo, "_pool_provider", lambda: clean_db)
    return clean_db


async def test_crea_poi_cambia_solo_quello_dato():
    p = await servizio.imposta(G, 1, ogni="6h", tipo="link", autore_id=5)
    assert (p.ogni_secondi, p.tipo, p.fissati, p.attiva) == (21600, "link", False, True)
    p = await servizio.imposta(G, 1, fissati=True)
    assert (p.ogni_secondi, p.tipo, p.fissati) == (21600, "link", True)
    p = await servizio.imposta(G, 1, attiva=False)
    assert p.attiva is False and (await repo.leggi(G, 1)).attiva is False


async def test_senza_intervallo_una_pulizia_nuova_non_nasce():
    with pytest.raises(lg.PuliziaNonValida):
        await servizio.imposta(G, 1, tipo="bot")


async def test_intervallo_o_tipo_storti():
    with pytest.raises(lg.PuliziaNonValida):
        await servizio.imposta(G, 1, ogni="5m")
    with pytest.raises(lg.PuliziaNonValida):
        await servizio.imposta(G, 1, ogni="6h", tipo="inventato")
    assert await repo.conta(G) == 0


async def test_tetto_per_server():
    for c in range(lg.MAX_RIGHE_PER_SERVER):
        await servizio.imposta(G, c + 1, ogni="1d")
    with pytest.raises(servizio.TroppePulizie):
        await servizio.imposta(G, 99, ogni="1d")
    await servizio.imposta(G, 1, ogni="2d")  # cambiarne una esistente si può
    await servizio.imposta(G + 1, 99, ogni="1d")  # un altro server ha il suo tetto


async def test_la_prima_pulizia_parte_dopo_un_intero_intervallo(db):
    await servizio.imposta(G, 1, ogni="1h")
    assert await repo.riserva_dovute(10) == []


async def test_riserva_dovute_segna_il_giro_prima_e_non_lo_ripete(db):
    await servizio.imposta(G, 1, ogni="1h")
    await servizio.imposta(G, 2, ogni="1h", attiva=False)
    await db.execute("UPDATE automod_pulizie SET ultimo_giro = now() - interval '2 hours'")
    dovute = await repo.riserva_dovute(10)
    assert [p.canale_id for p in dovute] == [1]  # la spenta no
    assert await repo.riserva_dovute(10) == []  # già segnata


async def test_riserva_rispetta_il_tetto_di_canali(db):
    for c in range(5):
        await servizio.imposta(G, c + 1, ogni="1h")
    await db.execute("UPDATE automod_pulizie SET ultimo_giro = now() - interval '2 hours'")
    assert len(await repo.riserva_dovute(3)) == 3


async def test_rimuovi_e_canale_cancellato():
    await servizio.imposta(G, 1, ogni="1d")
    assert await servizio.rimuovi(G, 1) is True
    assert await servizio.rimuovi(G, 1) is False
    await servizio.imposta(G, 2, ogni="1d")
    await servizio.canale_cancellato(G, 2)
    assert await repo.conta(G) == 0
