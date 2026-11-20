"""
tests/test_deposito_rps_b14.py
==============================
Deposito vincolato e sasso-carta-forbici con puntata (#125 B14): ECO-005, ECO-097; e le puntate sui giochi di
fortuna già esistenti (ECO-092 slot, ECO-095 monetina, ECO-096 dadi) provate qui sul loro vero motore.
Funzioni coperte: catalogo #125
"""

import asyncio
import random
from types import SimpleNamespace

import pytest

from core.coin_games_logic import gioca_dadi, gioca_monetina, gioca_rps, gioca_slot, ritorno_atteso_slot
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.rischio_repo import RischioRepository
from tests.support.concorrenza import apri_connessioni

G = 100


def test_puntate_su_slot_monetina_dadi_e_rps_con_vantaggio_del_banco():
    rng = random.Random(9)
    assert ritorno_atteso_slot(100) < 1  # ECO-092
    n = 20000
    for gioco in (lambda: gioca_monetina("testa", 100, rng), lambda: gioca_dadi(100, rng), lambda: gioca_rps("sasso", 100, rng)):  # ECO-095/096/097
        assert sum(gioco().restituzione - 100 for _ in range(n)) / n < 3  # nessun guadagno sistematico per il giocatore
    assert sum(gioca_rps("carta", 100, rng).restituzione for _ in range(n)) / n < 100
    assert {gioca_rps("sasso", 10, rng).restituzione for _ in range(300)} == {0, 10, 19}
    with pytest.raises(ValueError):
        gioca_rps("lizard", 10, rng)
    assert gioca_slot(10, rng).restituzione >= 0


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(rk=RischioRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db), pool=clean_db)


@pytest.mark.asyncio
async def test_deposito_blocca_la_banca_e_paga_l_interesse_una_volta(r):
    await r.lev.add_coins(G, 1, 100)
    await r.rk.deposita(G, 1, 100)
    assert await r.rk.blocca(G, 1, 101) == "poche"
    assert (await r.rk.banca(G, 1)).banca == 100 and await r.rk.deposito_di(G, 1) is None  # niente di scritto
    assert await r.rk.blocca(G, 1, 60) == "ok" and (await r.rk.banca(G, 1)).banca == 40
    assert await r.rk.blocca(G, 1, 10) == "gia" and (await r.rk.banca(G, 1)).banca == 40
    esito, resto = await r.rk.sblocca(G, 1)
    assert esito == "presto" and resto > 6 * 86400
    assert await r.rk.sblocca(G, 2) == ("niente", 0)
    await r.pool.execute("UPDATE economia_depositi SET scade_at = now() - interval '1 second'")
    await apri_connessioni(r.pool, 3)
    esiti = await asyncio.gather(*[r.rk.sblocca(G, 1) for _ in range(3)])
    assert [e for e in esiti if e[0] == "ok"] == [("ok", 66)]
    assert (await r.rk.banca(G, 1)).banca == 40 + 66
    for brutto in ((0, 7), (10, 0)):
        with pytest.raises(ValueError):
            await r.rk.blocca(G, 1, *brutto)
