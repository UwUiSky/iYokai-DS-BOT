"""
tests/test_potenziamenti_b10.py
===============================
Potenziamenti, scrigno, cambio del giorno e tabella dei guadagni (#125 B10): ECO-077, 079, 081, 082.
Funzioni coperte: catalogo #125
"""

import asyncio
import random
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from core.leveling_logic import con_potenziamento, costo_potenziamento, prezzo_rivendita, tasso_del_giorno
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.potenziamenti_repo import PotenziamentiRepository
from core.rischio_logic import PREMI_SCRIGNO, PREZZO_SCRIGNO, premio_scrigno, resa_scrigno
from tests.support.concorrenza import apri_connessioni

G = 100


def test_logica_cambio_potenziamenti_e_scrigno():
    giorni = {tasso_del_giorno(G, date(2026, 1, 1) + timedelta(days=n)) for n in range(200)}
    assert min(giorni) >= 40 and max(giorni) <= 60 and len(giorni) > 10
    assert tasso_del_giorno(G, date(2026, 5, 5)) == tasso_del_giorno(G, date(2026, 5, 5))
    assert prezzo_rivendita(100, 60) == 60 and prezzo_rivendita(100, 500) == 99 and prezzo_rivendita(100, -5) == 0
    assert [costo_potenziamento(n) for n in (0, 1, 4, 5, -1)] == [500, 1000, 8000, None, None]
    assert con_potenziamento(100, 0) == 100 and con_potenziamento(100, 3) == 130 and con_potenziamento(100, 99) == 150
    assert abs(sum(p for p, _ in PREMI_SCRIGNO) - 100) < 1e-9 and resa_scrigno() < 1
    rng = random.Random(2)
    assert {premio_scrigno(rng) for _ in range(3000)} == {v for _, v in PREMI_SCRIGNO}


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        p=PotenziamentiRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        cassa=GuildChestRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


@pytest.mark.asyncio
async def test_potenziamento_sale_di_un_livello_per_pagamento_anche_insieme(r):
    await r.lev.add_coins(G, 1, 500)
    assert await r.p.compra(G, 1, "lavoro") == ("ok", 1)
    assert await r.p.compra(G, 1, "lavoro") == ("poche", 1000)
    assert (await r.lev.get_totals(G, 1)).coins_total == 0 and await r.cassa.get_balance(G) == 500
    await r.lev.add_coins(G, 2, 600)
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.p.compra(G, 2, "premio") for _ in range(4)])
    assert [e[0] for e in esiti].count("ok") == 1 and (await r.p.livelli(G, 2))["premio"] == 1
    assert (await r.lev.get_totals(G, 2)).coins_total == 100
    with pytest.raises(ValueError):
        await r.p.compra(G, 1, "boh")
    await r.lev.add_coins(G, 3, 100_000)
    for _ in range(5):
        assert (await r.p.compra(G, 3, "lavoro"))[0] == "ok"
    assert (await r.p.compra(G, 3, "lavoro"))[0] == "massimo"


@pytest.mark.asyncio
async def test_scrigno_prezzo_premio_e_pausa(r):
    await r.lev.add_coins(G, 1, 100)
    assert await r.p.scrigno(G, 1, PREZZO_SCRIGNO, 50) == 50
    assert await r.cassa.get_balance(G) == PREZZO_SCRIGNO
    assert await r.p.scrigno(G, 1, PREZZO_SCRIGNO, 0) is None  # pausa (e non ha il prezzo)
    await r.lev.add_coins(G, 2, 99)
    assert await r.p.scrigno(G, 2, PREZZO_SCRIGNO, 800) is None  # saldo non basta: niente premio
    assert (await r.lev.get_totals(G, 2)).coins_total == 99
    await r.lev.add_coins(G, 3, 100)
    assert await r.p.scrigno(G, 3, PREZZO_SCRIGNO, 0) == 0
    for brutto in ((0, 1), (100, -1)):
        with pytest.raises(ValueError):
            await r.p.scrigno(G, 4, *brutto)
