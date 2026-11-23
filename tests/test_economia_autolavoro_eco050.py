"""
tests/test_economia_autolavoro_eco050.py
========================================
ECO-050 (D121): il lavoro automatico ogni 4 ore, solo con il premium del server. Database vero.
"""

import random

import pytest

from core import economia_autolavoro as al
from core import premium as premium_mod
from core.database import db
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo

G, U = 940001, 950001


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    leveling_settings_repo._cache.clear()
    await db.ensure_guild_exists(G)
    await db.set_module_active_for_guild(G, "leveling", True)
    yield
    database_module.db._modules_cache.clear()


@pytest.fixture
def premium(monkeypatch):
    stato = {"si": True}

    async def _ha(guild_id, modulo, bot=None):
        return stato["si"]

    monkeypatch.setattr(premium_mod, "guild_has_premium_access", _ha)
    return stato


async def _monete():
    return (await leveling_repo.get_totals(G, U)).coins_total


async def _scaduto():
    await db.pool.execute("UPDATE economia_autolavoro SET prossimo_at = now() - interval '1 minute'")


async def test_senza_premium_non_si_accende(premium):
    premium["si"] = False
    assert await al.accendi(G, U) is False
    assert not await al.acceso(G, U)


async def test_il_turno_paga_una_volta_e_si_sposta_di_4_ore(premium):
    assert await al.accendi(G, U) is True
    assert await al.tick(rng=random.Random(1)) == 1
    prima = await _monete()
    assert prima > 0
    assert await al.tick(rng=random.Random(1)) == 0  # non scaduto: niente doppio pagamento
    assert await _monete() == prima
    ore = await db.pool.fetchval("SELECT EXTRACT(EPOCH FROM prossimo_at - now())/3600 FROM economia_autolavoro")
    assert 3.9 < ore <= 4


async def test_un_secondo_giro_insieme_non_paga_due_volte(premium):
    await al.accendi(G, U)
    import asyncio

    r = await asyncio.gather(al.tick(rng=random.Random(2)), al.tick(rng=random.Random(2)))
    assert sum(r) == 1


async def test_se_l_attesa_del_lavoro_manuale_non_e_finita_il_turno_salta(premium):
    await al.accendi(G, U)
    await al.tick(rng=random.Random(3))
    prima = await _monete()
    await _scaduto()
    assert await al.tick(rng=random.Random(3)) == 0  # il lavoro era appena stato fatto
    assert await _monete() == prima
    assert await al.acceso(G, U)


async def test_perso_il_premium_la_riga_si_toglie(premium):
    await al.accendi(G, U)
    premium["si"] = False
    assert await al.tick() == 0
    assert not await al.acceso(G, U)


async def test_modulo_livelli_spento_toglie_la_riga(premium):
    await al.accendi(G, U)
    await db.set_module_active_for_guild(G, "leveling", False)
    assert await al.tick() == 0
    assert not await al.acceso(G, U)


async def test_spegni():
    await db.pool.execute("INSERT INTO economia_autolavoro VALUES ($1,$2,now())", G, U)
    assert await al.spegni(G, U) is True
    assert await al.spegni(G, U) is False
