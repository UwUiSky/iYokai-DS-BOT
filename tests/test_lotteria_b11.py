"""
tests/test_lotteria_b11.py
==========================
Lotteria giornaliera, registro e rimborso delle perdite (#125 B11): ECO-117, ECO-118, ECO-121.
Funzioni coperte: catalogo #125
"""

import asyncio
from collections import Counter
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from core.repositories.economia_repo import EconomiaRepository
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.lotteria_repo import MAX_BIGLIETTI_AL_GIORNO, LotteriaRepository
from tests.support.concorrenza import apri_connessioni

G = 100
OGGI = date(2026, 11, 20)


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        l=LotteriaRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        eco=EconomiaRepository(pool_provider=lambda: clean_db), cassa=GuildChestRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


@pytest.mark.asyncio
async def test_compra_biglietti_con_saldo_e_massimo_giornaliero(r):
    await r.lev.add_coins(G, 1, 100)
    assert await r.l.compra(G, 1, OGGI, 10, 3) == 3
    assert (await r.lev.get_totals(G, 1)).coins_total == 70
    assert await r.l.compra(G, 1, OGGI, 10, 8) is None  # 11 > 10: niente tolto
    assert (await r.lev.get_totals(G, 1)).coins_total == 70
    assert await r.l.compra(G, 1, OGGI, 100, 1) is None  # saldo non basta: il biglietto non resta scritto
    assert await r.l.miei(G, 1, OGGI) == (3, 3)
    for brutto in ((0, 1), (10, 0), (10, MAX_BIGLIETTI_AL_GIORNO + 1)):
        with pytest.raises(ValueError):
            await r.l.compra(G, 1, OGGI, *brutto)


@pytest.mark.asyncio
async def test_estrazione_una_volta_sola_pagamento_e_cassa(r):
    for u in (1, 2, 3):
        await r.lev.add_coins(G, u, 100)
        await r.l.compra(G, u, OGGI - timedelta(days=1), 10, 2)  # 60 spesi in tutto
    assert await r.l.estrai(G, OGGI - timedelta(days=1)) == []  # oggi stesso non si estrae
    await apri_connessioni(r.pool, 3)
    esiti = await asyncio.gather(*[r.l.estrai(G, OGGI) for _ in range(3)])
    fatte = [e for lista in esiti for e in lista]
    assert len(fatte) == 1 and fatte[0].premio == 54 and fatte[0].partecipanti == 3
    assert await r.cassa.get_balance(G) == 6
    tot = sum([(await r.lev.get_totals(G, u)).coins_total for u in (1, 2, 3)])
    assert tot == 300 - 60 + 54  # niente creato
    assert [x["vincitore"] for x in await r.l.registro(G)] == [fatte[0].vincitore]
    assert await r.l.estrai(G, OGGI) == []


@pytest.mark.asyncio
async def test_il_vincitore_dipende_dai_biglietti(r):
    vinti = Counter()
    for n in range(60):
        giorno = date(2026, 1, 1) + timedelta(days=n)
        await r.lev.add_coins(G, 1, 10)
        await r.lev.add_coins(G, 2, 10)
        await r.l.compra(G, 1, giorno, 1, 1)
        await r.l.compra(G, 2, giorno, 1, 9)
    for e in await r.l.estrai(G, date(2026, 6, 1)):
        vinti[e.vincitore] += 1
    assert sum(vinti.values()) == 60 and vinti[2] > vinti[1]
    assert await r.l.guild_con_biglietti(date(2026, 6, 1)) == []


@pytest.mark.asyncio
async def test_rimborso_solo_sulle_perdite_nette_e_una_volta(r):
    await r.eco.registra_partita(G, 1, "slot", 100, 0)
    await r.eco.registra_partita(G, 1, "slot", 100, 0)
    assert await r.l.rimborso(G, 1, 10) == 20
    assert await r.l.rimborso(G, 1, 10) is None  # niente di nuovo
    await r.eco.registra_partita(G, 1, "dadi", 100, 200)  # vince 100
    assert await r.l.rimborso(G, 1, 10) is None
    await r.eco.registra_partita(G, 1, "dadi", 100, 0)  # perde 100: la vincita di prima compensa
    assert await r.l.rimborso(G, 1, 10) is None
    await r.eco.registra_partita(G, 1, "slot", 100, 0)  # ora netto -100 dalla base
    assert await r.l.rimborso(G, 1, 10) == 10
    assert (await r.lev.get_totals(G, 1)).coins_total == 30
    await apri_connessioni(r.pool, 3)
    await r.eco.registra_partita(G, 2, "slot", 100, 0)
    esiti = await asyncio.gather(*[r.l.rimborso(G, 2, 10) for _ in range(3)])
    assert [e for e in esiti if e] == [10]
    for brutto in (0, 21, -1):
        with pytest.raises(ValueError):
            await r.l.rimborso(G, 1, brutto)
