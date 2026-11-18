"""
tests/test_rischio_b6.py
========================
Banca, lavori, colpo, furto, elemosina e cerca (#125 B6): ECO-004, 029, 030, 031, 032, 040, 041.
PostgreSQL vero; pause e saldi provati con richieste insieme.
Funzioni coperte: catalogo #125
"""

import asyncio
import random
from types import SimpleNamespace

import pytest

from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from core.repositories.rischio_repo import EsitoFurto, RischioRepository
from core.rischio_logic import (
    LAVORI, LUOGHI, cerca, elemosina, gioca_colpo, importo_furto, lavoro_per_turni, multa_furto, paga_con_lavoro,
    turni_alla_promozione,
)
from tests.support.concorrenza import apri_connessioni

G = 100


class _Fisso:
    def __init__(self, *v):
        self.v = list(v)

    def randint(self, a, b):
        return self.v.pop(0)


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        rk=RischioRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        imp=LevelingSettingsRepository(pool_provider=lambda: clean_db),
        cassa=GuildChestRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


def test_logica_lavori_colpo_furto_cerca():
    assert lavoro_per_turni(0)[0] == "stagista" and lavoro_per_turni(10)[0] == "commesso" and lavoro_per_turni(9999)[0] == LAVORI[-1][0]
    assert turni_alla_promozione(0) == 10 and turni_alla_promozione(9999) is None
    assert paga_con_lavoro(100, 130) == 130 and paga_con_lavoro(-5, 130) == 0
    assert gioca_colpo(_Fisso(100, 1), 40, 10, 20, 500).riuscito  # premio 100, tiro 1 <= 40
    e = gioca_colpo(_Fisso(100, 99), 40, 10, 20, 30)
    assert (e.riuscito, e.importo) == (False, 30)  # multa 50 ma ha solo 30
    assert gioca_colpo(_Fisso(100, 99), 40, 10, 20, 0).importo == 0
    assert importo_furto(49, 10) == 0 and importo_furto(1000, 10) == 100 and importo_furto(10**9, 50) == 5000
    assert multa_furto(100, 30) == 30 and multa_furto(100, 500) == 50
    assert elemosina(_Fisso(10)) == 0 and elemosina(_Fisso(90, 7)) == 7
    for luogo in LUOGHI:
        assert cerca(_Fisso(1, LUOGHI[luogo][1]), luogo) == LUOGHI[luogo][1]
        assert cerca(_Fisso(100, 5), luogo) == 0 if LUOGHI[luogo][0] < 100 else True
    with pytest.raises(ValueError):
        cerca(random.Random(), "luna")


@pytest.mark.asyncio
async def test_banca_deposito_prelievo_e_tetto(r):
    await r.lev.add_coins(G, 1, 100)
    assert await r.rk.deposita(G, 1, 101) is None
    b = await r.rk.deposita(G, 1, 60)
    assert (b.contanti, b.banca) == (40, 60)
    assert await r.rk.preleva(G, 1, 61) is None
    await r.imp.set_options(G, tetto_saldo=50)
    assert await r.rk.preleva(G, 1, 20) is None  # 40+20 > 50
    assert (await r.rk.preleva(G, 1, 10)).contanti == 50
    for brutto in (0, -3):
        with pytest.raises(ValueError):
            await r.rk.deposita(G, 1, brutto)
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.rk.deposita(G, 1, 50) for _ in range(4)])
    assert [e for e in esiti if e] == [e for e in esiti if e][:1] and len([e for e in esiti if e]) == 1  # 50 contanti: uno solo
    tot = await r.rk.banca(G, 1)
    assert tot.contanti + tot.banca == 100


@pytest.mark.asyncio
async def test_pausa_dei_guadagni_una_volta_anche_insieme(r):
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.rk.guadagna(G, 1, "cerca", 3600, 20) for _ in range(4)])
    assert len([e for e in esiti if e is not None]) == 1
    assert (await r.lev.get_totals(G, 1)).coins_total == 20
    assert await r.rk.guadagna(G, 2, "cerca", 3600, 0) == 0  # «niente» consuma la pausa
    assert await r.rk.guadagna(G, 2, "cerca", 3600, 5) is None
    assert await r.rk.pausa_rimasta(G, 2, "cerca", 3600) > 3000
    with pytest.raises(ValueError):
        await r.rk.guadagna(G, 3, "x", 60, -1)


@pytest.mark.asyncio
async def test_colpo_riuscito_multa_alla_cassa_e_mai_sotto_zero(r):
    await r.lev.add_coins(G, 1, 30)
    assert await r.rk.colpo(G, 1, "colpo", 7200, False, 50) == (-30, 0)  # multa 50, ha 30
    assert (await r.cassa.get_balance(G)) == 30
    assert await r.rk.colpo(G, 1, "colpo", 7200, True, 99) is None  # pausa
    assert await r.rk.colpo(G, 2, "colpo", 7200, True, 99) == (99, 99)
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.rk.colpo(G, 3, "colpo", 7200, True, 10) for _ in range(4)])
    assert len([e for e in esiti if e]) == 1 and (await r.lev.get_totals(G, 3)).coins_total == 10


@pytest.mark.asyncio
async def test_furto_riuscito_fallito_protezione_e_pochi_contanti(r):
    await r.lev.add_coins(G, 1, 200)  # ladro
    await r.lev.add_coins(G, 2, 1000)  # vittima
    f = await r.rk.furto(G, 1, 2, True, 10, 3600)
    assert (f.esito, f.importo) == (EsitoFurto.RIUSCITO, 100)
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [300, 900]
    assert (await r.rk.furto(G, 1, 3, True, 10, 3600)).esito is EsitoFurto.POCHI_CONTANTI  # 3 non ha contanti
    await r.lev.add_coins(G, 3, 1000)
    assert (await r.rk.furto(G, 1, 3, True, 10, 3600)).esito is EsitoFurto.PAUSA  # il ladro è in pausa
    await r.lev.add_coins(G, 4, 500)
    f = await r.rk.furto(G, 4, 2, True, 10, 3600)  # 2 è protetto da poco
    assert f.esito is EsitoFurto.PROTETTO
    assert (await r.lev.get_totals(G, 4)).coins_total == 500
    assert (await r.rk.furto(G, 4, 3, False, 10, 3600)).esito is EsitoFurto.FALLITO  # la pausa di 4 non era stata bruciata
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (4, 3)] == [450, 1050]  # multa 50 alla vittima
    with pytest.raises(ValueError):
        await r.rk.furto(G, 1, 1, True, 10, 3600)


@pytest.mark.asyncio
async def test_furti_incrociati_insieme_non_creano_ne_perdono_monete(r):
    for u in (1, 2):
        await r.lev.add_coins(G, u, 1000)
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(
        *[r.rk.furto(G, 1, 2, True, 10, 3600), r.rk.furto(G, 2, 1, True, 10, 3600)] * 2, return_exceptions=True
    )
    assert not [e for e in esiti if isinstance(e, Exception)]
    assert sum([(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)]) == 2000


@pytest.mark.asyncio
async def test_turni_di_lavoro_e_dimissioni(r):
    assert await r.rk.turni(G, 1) == 0
    assert [await r.rk.segna_turno(G, 1) for _ in range(3)] == [1, 2, 3]
    assert await r.rk.dimettiti(G, 1) == 3 and await r.rk.turni(G, 1) == 0
    assert await r.rk.dimettiti(G, 1) == 0
