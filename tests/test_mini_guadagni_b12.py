"""
tests/test_mini_guadagni_b12.py
===============================
Piccoli guadagni (scava, meme, coccole, gratta, bersaglio) e azioni degli oggetti (#125 B12): ECO-042, 043, 044,
046, 047, 060. Funzioni coperte: catalogo #125
"""

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.repositories.inventario_repo import InventarioRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.potenziamenti_repo import PotenziamentiRepository
from core.repositories.shop_repo import ShopRepository
from core.rischio_logic import (
    MEME, PREMI_GRATTA, PREZZO_GRATTA, coccole, premio_bersaglio, premio_gratta, pubblica_meme, resa_gratta, scava,
)
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


def test_logica_dei_piccoli_guadagni():
    rng = random.Random(4)
    assert {scava(rng) for _ in range(3000)} >= {0, 200} and all(v in (0, 200) or 15 <= v <= 60 for v in (scava(rng) for _ in range(3000)))
    for tipo, (_, lo, hi) in MEME.items():
        dati = {pubblica_meme(rng, tipo) for _ in range(500)}
        assert 0 in dati or tipo == "di nicchia"
        assert all(d == 0 or lo <= d <= hi for d in dati)
    with pytest.raises(ValueError):
        pubblica_meme(rng, "boh")
    assert all(1 <= coccole(rng) <= 5 and 5 <= premio_bersaglio(rng) <= 15 for _ in range(200))
    assert abs(sum(p for p, _ in PREMI_GRATTA) - 100) < 1e-9 and resa_gratta() < 1
    assert {premio_gratta(rng) for _ in range(3000)} == {v for _, v in PREMI_GRATTA}


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        p=PotenziamentiRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        inv=InventarioRepository(pool_provider=lambda: clean_db), shop=ShopRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


@pytest.mark.asyncio
async def test_gratta_costa_paga_e_ha_la_sua_pausa(r):
    await r.lev.add_coins(G, 1, 100)
    assert await r.p.scrigno(G, 1, PREZZO_GRATTA, 50, "gratta", 60) == 130
    assert await r.p.scrigno(G, 1, PREZZO_GRATTA, 300, "gratta", 60) is None  # pausa del gratta
    assert await r.p.scrigno(G, 1, 100, 0) == 30  # lo scrigno ha una pausa a parte


@pytest.mark.asyncio
async def test_azione_monete_toglie_il_pezzo_e_paga_insieme(r):
    nuovo = await r.shop.add_item(G, "Borsa", 10, None, None)
    item = await r.shop.get_item(nuovo if isinstance(nuovo, int) else nuovo.id, G)
    await r.lev.add_coins(G, 1, 10)
    await r.shop.buy_item(G, 1, item)
    assert await r.shop.imposta_azione(item.id, G, "monete", 40) is True
    assert (await r.shop.get_item(item.id, G)).azione == "monete"
    assert await r.inv.usa_con_monete(G, 1, item.id, 40) == 40
    assert await r.inv.usa_con_monete(G, 1, item.id, 40) is None  # pezzo finito: niente monete
    assert (await r.lev.get_totals(G, 1)).coins_total == 40
    await r.inv.restituisci(G, 1, item.id)
    assert (await r.inv.lista(G, 1))[0].quantita == 1
    for brutto in (("monete", 0), ("monete", 100_001), ("ruolo_dai", None), ("boh", 5)):
        with pytest.raises(ValueError):
            await r.shop.imposta_azione(item.id, G, *brutto)
    assert await r.shop.imposta_azione(item.id, G + 1, "nessuna", None) is False
    with pytest.raises(ValueError):
        await r.inv.usa_con_monete(G, 1, item.id, 0)


@pytest.mark.asyncio
async def test_comando_usa_con_ruolo_non_assegnabile_non_consuma(r, monkeypatch):
    import cogs.leveling.inventario as m
    from tests.support.moduli import attiva_livelli
    await attiva_livelli(monkeypatch, r.pool, G)
    monkeypatch.setattr(m, "inventario_repo", r.inv)
    monkeypatch.setattr(m, "shop_repo", r.shop)
    cog = m.InventarioCog(bot=None)
    nuovo = await r.shop.add_item(G, "Distintivo", 5, None, None)
    item = await r.shop.get_item(nuovo if isinstance(nuovo, int) else nuovo.id, G)
    await r.lev.add_coins(G, 1, 5)
    await r.shop.buy_item(G, 1, item)
    await r.shop.imposta_azione(item.id, G, "ruolo_dai", 777)
    guild = fake_guild(G)
    guild.get_role = MagicMock(return_value=None)  # il ruolo non esiste più
    i = fake_interaction(guild=guild, user=fake_member(1))
    await cog.usa.callback(cog, i, item.id)
    assert i.response.send_message.await_args.kwargs.get("ephemeral") is True
    assert (await r.inv.lista(G, 1))[0].quantita == 1  # pezzo intatto
