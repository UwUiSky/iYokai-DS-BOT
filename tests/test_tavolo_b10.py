"""
tests/test_tavolo_b10.py
========================
Tris e forza 4 tra utenti, con o senza puntata (#125 B10): ECO-107, ECO-108, ECO-109.
Funzioni coperte: catalogo #125
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.fun.tavolo import TavoloCog, TavoloView
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.partite_repo import PartiteRepository
from core.tavolo_logic import metti_f4, metti_tris, nuova_griglia, piena, vincitore_f4, vincitore_tris
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


def test_logica_tris_e_forza4():
    g = nuova_griglia(3, 3)
    for r, c, p in ((0, 0, 1), (1, 1, 2), (0, 1, 1), (2, 2, 2)):
        assert metti_tris(g, r, c, p)
    assert not metti_tris(g, 0, 0, 2) and not metti_tris(g, 3, 0, 1) and vincitore_tris(g) == 0
    metti_tris(g, 0, 2, 1)
    assert vincitore_tris(g) == 1
    pieno = [[1, 2, 1], [1, 2, 2], [2, 1, 1]]
    assert piena(pieno) and vincitore_tris(pieno) == 0
    f = nuova_griglia(6, 7)
    for _ in range(3):
        metti_f4(f, 2, 1)
        metti_f4(f, 3, 2)
    assert vincitore_f4(f) == 0
    metti_f4(f, 2, 1)
    assert vincitore_f4(f) == 1  # quattro in verticale
    d = nuova_griglia(6, 7)
    for i in range(4):
        d[5 - i][i] = 2
    assert vincitore_f4(d) == 2  # diagonale
    colonna = nuova_griglia(6, 7)
    assert [metti_f4(colonna, 0, 1) for _ in range(7)] == [5, 4, 3, 2, 1, 0, None] and metti_f4(colonna, 9, 1) is None


@pytest.fixture
def r(clean_db, monkeypatch):
    import cogs.fun.tavolo as m
    import core.ui_base as ui

    async def nessuno(*a, **k):
        return False

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    p = PartiteRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(m, "partite_repo", p)
    from core.repositories.leveling_settings_repo import LevelingSettingsRepository
    monkeypatch.setattr(m, "leveling_settings_repo", LevelingSettingsRepository(pool_provider=lambda: clean_db))
    return SimpleNamespace(p=p, lev=LevelingRepository(pool_provider=lambda: clean_db), pool=clean_db)


def _i(membro):
    i = fake_interaction(guild=fake_guild(G), user=membro)
    i.response.edit_message = AsyncMock()
    return i


@pytest.mark.asyncio
async def test_partita_con_puntata_vince_chi_fa_tris_e_incassa_il_doppio(r):
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 100)
    a, b = fake_member(1), fake_member(2)
    v = TavoloView("tris", G, a, b, 40, "coin")
    await v._accetta(_i(a))  # lo sfidante non accetta
    assert v.fase == "attesa" and (await r.lev.get_totals(G, 1)).coins_total == 100
    await v._accetta(_i(b))
    assert v.fase == "in_corso" and [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [60, 60]
    await v._accetta(_i(b))  # secondo clic: niente di nuovo
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [60, 60]
    mosse = [(a, 0, 0), (b, 1, 0), (a, 0, 1), (b, 1, 1), (a, 0, 2)]
    for chi, rr, cc in mosse:
        await v._mossa_tris(rr, cc)(_i(chi))
    assert v.fase == "fine"
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [140, 60]
    await v._fine(None, 2)  # chiusura doppia: niente
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [140, 60]


@pytest.mark.asyncio
async def test_turni_estranei_e_pareggio_restituiscono_le_puntate(r):
    await r.lev.add_coins(G, 1, 50)
    await r.lev.add_coins(G, 2, 50)
    a, b = fake_member(1), fake_member(2)
    v = TavoloView("tris", G, a, b, 50, "coin")
    await v._accetta(_i(b))
    est = _i(fake_member(9))
    assert await v.interaction_check(est) is False
    ie = _i(b)
    await v._mossa_tris(0, 0)(ie)  # tocca ad a
    assert ie.response.send_message.await_args.kwargs["ephemeral"] is True
    await v._fine(None, 0)
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [50, 50]


@pytest.mark.asyncio
async def test_saldo_insufficiente_annulla_e_restituisce_il_primo_prelievo(r):
    await r.lev.add_coins(G, 1, 80)
    await r.lev.add_coins(G, 2, 10)
    a, b = fake_member(1), fake_member(2)
    v = TavoloView("forza4", G, a, b, 50, "coin")
    await v._accetta(_i(b))
    assert v.fase == "fine"
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [80, 10]


@pytest.mark.asyncio
async def test_senza_puntata_e_timeout_perde_chi_deve_muovere(r):
    a, b = fake_member(1), fake_member(2)
    v = TavoloView("forza4", G, a, b, 0, "coin")
    await v._accetta(_i(b))
    assert v.fase == "in_corso"
    for chi, col in ((a, 0), (b, 1), (a, 0), (b, 1), (a, 0), (b, 1), (a, 0)):
        await v._mossa_f4(col)(_i(chi))
    assert v.fase == "fine"
    v2 = TavoloView("tris", G, a, b, 0, "coin")
    v2.messaggio = _i(a)
    v2.messaggio.edit_original_response = AsyncMock()
    await v2._accetta(_i(b))
    await v2.on_timeout()
    assert v2.fase == "fine"
