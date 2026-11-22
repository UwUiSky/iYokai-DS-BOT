"""
tests/test_contenuti_r6.py
==========================
Comandi di guadagno del server (ECO-039), righe del profilo (ECO-152). Funzioni coperte: catalogo #125
"""

import asyncio
from types import SimpleNamespace

import pytest

from cogs.leveling.contenuti import leggi_righe
from core.repositories.contenuti_repo import MAX_COMANDI_GUADAGNO, RIGHE_PROFILO, ContenutiRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.rischio_repo import RischioRepository
from tests.support.concorrenza import apri_connessioni

G = 100


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(c=ContenutiRepository(pool_provider=lambda: clean_db), ris=RischioRepository(pool_provider=lambda: clean_db),
                           lev=LevelingRepository(pool_provider=lambda: clean_db), pool=clean_db)


def test_lettura_delle_righe():
    assert leggi_righe("banca, monete") == ["banca", "monete"]
    for brutto in ("", "monete,monete", "boh", " , "):
        assert leggi_righe(brutto) is None


@pytest.mark.asyncio
async def test_righe_del_profilo_ordine_scelto_e_di_base_tutte(r):
    assert await r.c.righe(G, 1) == list(RIGHE_PROFILO)
    await r.c.imposta_righe(G, 1, ["prestigio", "monete"])
    assert await r.c.righe(G, 1) == ["prestigio", "monete"] and await r.c.righe(G, 2) == list(RIGHE_PROFILO)


@pytest.mark.asyncio
async def test_comando_di_guadagno_tetto_nome_doppio_e_pausa_atomica(r):
    assert await r.c.crea_comando(G, "caccia", 5, 10, 3600, "Bottino: {monete}", 9) == "ok"
    assert await r.c.crea_comando(G, "caccia", 5, 10, 3600, "x", 9) == "esiste"
    for i in range(MAX_COMANDI_GUADAGNO - 1):
        assert await r.c.crea_comando(G, f"c{i}", 1, 2, 60, "x", 9) == "ok"
    assert await r.c.crea_comando(G, "ultimo", 1, 2, 60, "x", 9) == "troppi"
    c = await r.c.comando(G, "caccia")
    assert (c.minimo, c.massimo, c.pausa_s) == (5, 10, 3600) and len(await r.c.comandi(G)) == MAX_COMANDI_GUADAGNO
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*(r.ris.guadagna(G, 1, "cmd:caccia", c.pausa_s, 7) for _ in range(3)))
    assert [e for e in esiti if e is not None] == [7] and (await r.lev.get_totals(G, 1)).coins_total == 7  # una sola riscossione
    assert await r.c.togli_comando(G, "caccia") and not await r.c.togli_comando(G, "caccia")
    with pytest.raises(Exception):
        await r.c.crea_comando(G, "Maiuscolo!", 1, 2, 60, "x", 9)  # il nome non valido lo ferma il database
