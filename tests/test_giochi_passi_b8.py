"""
tests/test_giochi_passi_b8.py
=============================
Più alto o più basso e torre (#125 B8): ECO-094, ECO-098. Resa media 95% per ogni strategia, chiusura unica.
Funzioni coperte: catalogo #125
"""

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.fun.giochi_passi import AltoBassoView, TorreView
from core.passi_logic import (
    TORRE_PROBABILITA, incasso, indovinato, moltiplicatore_passo, passo_possibile, probabilita_scelta, torre_moltiplicatore,
)
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.partite_repo import PartiteRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


def test_ogni_passo_rende_in_media_il_95_percento():
    for carta in range(1, 14):
        for scelta in ("alto", "basso"):
            if passo_possibile(carta, scelta):
                assert abs(probabilita_scelta(carta, scelta) * moltiplicatore_passo(carta, scelta) - 0.95) < 1e-9
    assert not passo_possibile(13, "alto") and not passo_possibile(1, "basso")
    with pytest.raises(ValueError):
        moltiplicatore_passo(13, "alto")
    assert not indovinato(7, 7, "alto") and not indovinato(7, 7, "basso") and indovinato(7, 9, "alto")
    p = 1.0
    for piano, prob in enumerate(TORRE_PROBABILITA, 1):
        p *= prob
        assert abs(p * torre_moltiplicatore(piano) - 0.95) < 1e-9
    assert torre_moltiplicatore(0) == 1.0
    with pytest.raises(ValueError):
        torre_moltiplicatore(len(TORRE_PROBABILITA) + 1)
    assert incasso(100, 1.239) == 123


def test_nessuna_strategia_batte_il_banco_alla_torre():
    rng = random.Random(5)
    n = 30000
    for ferma in (1, 3, 6):
        tot = 0
        for _ in range(n):
            piano = 0
            while piano < ferma:
                piano += 1
                if rng.random() >= TORRE_PROBABILITA[piano - 1]:
                    piano = -1
                    break
            tot += incasso(100, torre_moltiplicatore(piano)) if piano > 0 else 0
        assert tot / n < 100


@pytest.fixture
def r(clean_db, monkeypatch):
    import cogs.fun.giochi_passi as m
    import core.ui_base as ui

    async def nessuno(*a, **k):
        return False

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    p = PartiteRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(m, "partite_repo", p)
    monkeypatch.setattr(m, "economia_repo", SimpleNamespace(registra_partita=AsyncMock()))
    return SimpleNamespace(p=p, lev=LevelingRepository(pool_provider=lambda: clean_db))


def _i(uid=1):
    i = fake_interaction(guild=fake_guild(G), user=fake_member(uid))
    i.response.edit_message = AsyncMock()
    return i


@pytest.mark.asyncio
async def test_alto_basso_giusta_poi_incassa_e_sbagliata_perde(r, monkeypatch):
    import cogs.fun.giochi_passi as m
    await r.lev.add_coins(G, 1, 100)
    a = await r.p.apri(G, 1, "alto-basso", 100, 0)
    v = AltoBassoView(a.partita_id, G, 1, 100, "coin")
    v.carta = 1
    v._aggiorna_bottoni()
    seq = iter([13, 2])
    monkeypatch.setattr(m, "estrai_carta", lambda rng: next(seq))
    assert v.incassa.disabled and v.basso.disabled
    await v.alto.callback(_i())  # 1 -> 13: giusta, 13 non ha «alto»
    assert v.indovinate == 1 and v.alto.disabled and not v.incassa.disabled
    assert v.ritorno_attuale() == int(100 * 0.95 / (12 / 13))
    await v.incassa.callback(_i())
    assert (await r.lev.get_totals(G, 1)).coins_total == 0 + v.ritorno_attuale()
    await v.incassa.callback(_i())  # già chiusa: niente di nuovo
    assert (await r.lev.get_totals(G, 1)).coins_total == v.ritorno_attuale()

    a2 = await r.p.apri(G, 2, "alto-basso", 50, 0) if await r.lev.add_coins(G, 2, 50) else None
    v2 = AltoBassoView(a2.partita_id, G, 2, 50, "coin")
    v2.carta = 7
    v2._aggiorna_bottoni()
    seq2 = iter([3])
    monkeypatch.setattr(m, "estrai_carta", lambda rng: next(seq2))
    await v2.alto.callback(_i(2))  # 7 -> 3 : sbagliata
    assert (await r.lev.get_totals(G, 2)).coins_total == 0 and v2.finito


@pytest.mark.asyncio
async def test_torre_sale_incassa_e_crolla(r, monkeypatch):
    import cogs.fun.giochi_passi as m
    await r.lev.add_coins(G, 1, 100)
    a = await r.p.apri(G, 1, "torre", 100, 0)
    v = TorreView(a.partita_id, G, 1, 100, "coin")
    assert v.incassa.disabled
    monkeypatch.setattr(m, "torre_crolla", lambda piano, rng: False)
    await v.sali.callback(_i())
    await v.sali.callback(_i())
    assert v.piani == 2 and not v.incassa.disabled
    atteso = incasso(100, torre_moltiplicatore(2))
    await v.incassa.callback(_i())
    assert (await r.lev.get_totals(G, 1)).coins_total == atteso
    await r.lev.add_coins(G, 2, 40)
    a2 = await r.p.apri(G, 2, "torre", 40, 0)
    v2 = TorreView(a2.partita_id, G, 2, 40, "coin")
    monkeypatch.setattr(m, "torre_crolla", lambda piano, rng: True)
    await v2.sali.callback(_i(2))
    assert (await r.lev.get_totals(G, 2)).coins_total == 0 and v2.finito


@pytest.mark.asyncio
async def test_estraneo_non_preme_e_timeout_incassa(r):
    await r.lev.add_coins(G, 1, 100)
    a = await r.p.apri(G, 1, "torre", 100, 0)
    v = TorreView(a.partita_id, G, 1, 100, "coin")
    assert await v.interaction_check(_i(2)) is False
    v.piani = 1
    v.messaggio = _i()
    v.messaggio.edit_original_response = AsyncMock()
    await v.on_timeout()
    assert (await r.lev.get_totals(G, 1)).coins_total == incasso(100, torre_moltiplicatore(1))
    await v.on_timeout()
    assert (await r.lev.get_totals(G, 1)).coins_total == incasso(100, torre_moltiplicatore(1))
