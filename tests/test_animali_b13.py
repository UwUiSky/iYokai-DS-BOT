"""
tests/test_animali_b13.py
=========================
Animali da accudire e pesca (#125 B13): ECO-122, 123, 124, 130, 131, 132, 133, 134, 138.
Funzioni coperte: catalogo #125
"""

import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.animali_logic import (
    LUOGHI_PESCA, PESCI, SPECIE, bonus_percentuale, costo_posto, livello, nome_valido, pesca, salute, valore_atteso_pesca,
    valore_pesci, valore_stato,
)
from core.repositories.animali_repo import AnimaliRepository
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository
from tests.support.concorrenza import apri_connessioni

G = 100
ADESSO = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


def test_logica_animali_e_pesca():
    assert valore_stato(ADESSO, ADESSO, "fame") == 100 and valore_stato(ADESSO - timedelta(hours=10), ADESSO, "fame") == 60
    assert valore_stato(ADESSO - timedelta(days=9), ADESSO, "gioco") == 0
    assert salute(ADESSO, ADESSO, ADESSO - timedelta(hours=100), ADESSO) == 66
    assert livello(0) == 0 and livello(120) == 2 and livello(10**6) == 10
    assert bonus_percentuale([("gatto", 80, 0)], "lavoro") == 5 and bonus_percentuale([("gatto", 29, 0)], "lavoro") == 0
    assert bonus_percentuale([("gatto", 80, 0), ("volpe", 80, 5)], "premio") == 9 and bonus_percentuale([("boh", 90, 0)], "premio") == 0
    assert bonus_percentuale([("volpe", 100, 10)], "premio") == 12 and bonus_percentuale([("civetta", 100, 10)], "premio") == 15
    assert [costo_posto(n) for n in (0, 1, 2, -1)] == [1000, 2000, None, None]
    assert nome_valido("  Mi  chi ") == "Mi chi"
    for brutto in ("", "x" * 21, "@everyone", "a`b"):
        with pytest.raises(ValueError):
            nome_valido(brutto)
    rng = random.Random(1)
    for luogo in LUOGHI_PESCA:
        assert valore_atteso_pesca(luogo) < 20  # con la pausa di 15 minuti meno di ~80 monete l'ora
        assert {pesca(rng, luogo) for _ in range(3000)} <= set(PESCI) | {None}
    with pytest.raises(ValueError):
        pesca(rng, "luna")
    assert valore_pesci({"sardina": 3, "luccio": 1, "boh": 9, "carpa": 0}) == 46


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        a=AnimaliRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        cassa=GuildChestRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


@pytest.mark.asyncio
async def test_acquisto_posti_e_cura(r):
    await r.lev.add_coins(G, 1, 400)
    assert await r.a.compra(G, 1, "gatto", "Micio") == "ok"
    assert (await r.lev.get_totals(G, 1)).coins_total == 100 and await r.cassa.get_balance(G) == 300
    assert await r.a.compra(G, 1, "rana", "Ra") == "pieno"  # un solo posto
    assert await r.a.compra_posto(G, 1) == ("poche", 1000)
    await r.lev.add_coins(G, 1, 5000)
    assert await r.a.compra_posto(G, 1) == ("ok", 1000)
    assert await r.a.compra(G, 1, "rana", "Ra") == "ok"
    with pytest.raises(ValueError):
        await r.a.compra(G, 1, "drago", "x")
    animali = await r.a.elenco(G, 1)
    gatto = animali[0]["id"]
    assert await r.a.cura(G, 1, gatto, "igiene") == "pausa"  # appena nato: curato adesso
    await r.pool.execute("UPDATE economia_animali SET fame_at = now() - interval '2 hours', igiene_at = now() - interval '2 hours'")
    saldo = (await r.lev.get_totals(G, 1)).coins_total
    assert await r.a.cura(G, 1, gatto, "fame") == "ok" and (await r.lev.get_totals(G, 1)).coins_total == saldo - 5
    assert await r.a.cura(G, 1, gatto, "fame") == "pausa" and (await r.lev.get_totals(G, 1)).coins_total == saldo - 5  # costo non perso
    assert await r.a.cura(G, 2, gatto, "igiene") == "non_tuo"
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.a.cura(G, 1, gatto, "igiene") for _ in range(4)])
    assert esiti.count("ok") == 1
    assert (await r.a.elenco(G, 1))[0]["xp"] == 10
    with pytest.raises(ValueError):
        await r.a.cura(G, 1, gatto, "x; DROP TABLE")


@pytest.mark.asyncio
async def test_posti_massimi_attivita_e_bonus(r):
    await r.lev.add_coins(G, 1, 10_000)
    assert [(await r.a.compra_posto(G, 1))[0] for _ in range(3)] == ["ok", "ok", "massimo"]
    await r.a.compra(G, 1, "volpe", "Kit")
    animale = (await r.a.elenco(G, 1))[0]["id"]
    assert await r.a.bonus(G, 1, "premio") == 6 and await r.a.bonus(G, 1, "lavoro") == 4
    assert await r.a.attivita(G, 1, animale, 10, True) is not None
    assert await r.a.attivita(G, 1, animale, 10, True) is None  # pausa di 2 ore
    assert await r.a.attivita(G, 1, animale, 10, False) is None and await r.a.attivita(G, 2, animale, 10, True) is None
    await r.pool.execute("UPDATE economia_animali SET fame_at = now() - interval '30 hours', igiene_at = now() - interval '60 hours', gioco_at = now() - interval '60 hours'")
    assert await r.a.bonus(G, 1, "premio") == 0  # trascurato: niente bonus


@pytest.mark.asyncio
async def test_pesca_deposito_vendita_guida_e_classifica(r):
    oggi = date(2026, 11, 20)
    assert await r.a.pesca(G, 1, oggi, "trota", 900) is True
    assert await r.a.pesca(G, 1, oggi, "luccio", 900) is None  # pausa
    await r.pool.execute("DELETE FROM economia_pause")
    assert await r.a.pesca(G, 1, oggi, None, 900) is False
    await r.pool.execute("DELETE FROM economia_pause")
    assert await r.a.pesca(G, 1, oggi, "trota", 900) is True
    assert await r.a.deposito(G, 1) == {"trota": 2} and await r.a.visti(G, 1) == {"trota"}
    assert [(x["user_id"], x["punti"]) for x in await r.a.classifica_giorno(G, oggi)] == [(1, 20)]
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.a.vendi_pesci(G, 1) for _ in range(4)])
    assert sorted(esiti)[-1] == (2, 20) and sum(e[1] for e in esiti) == 20
    assert (await r.lev.get_totals(G, 1)).coins_total == 20 and await r.a.deposito(G, 1) == {}
    with pytest.raises(ValueError):
        await r.pool.execute("DELETE FROM economia_pause")
        await r.a.pesca(G, 1, oggi, "balena", 900)
