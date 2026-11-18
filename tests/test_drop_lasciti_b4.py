"""
tests/test_drop_lasciti_b4.py
=============================
Monete lasciate in un canale e drop regolabili (#125 B4): ECO-052, ECO-053, ECO-055.
PostgreSQL vero; prese e rimborsi provati con richieste insieme.
Funzioni coperte: SPEC §15.6, catalogo #125
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.leveling.drop import DropCog
from cogs.leveling.leveling import LevelingCog
from core.repositories.lasciti_repo import LascitiRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository, leveling_settings_repo
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

G = 100


@pytest.fixture
def r(clean_db):
    return type("R", (), dict(
        las=LascitiRepository(pool_provider=lambda: clean_db),
        lev=LevelingRepository(pool_provider=lambda: clean_db),
        imp=LevelingSettingsRepository(pool_provider=lambda: clean_db),
        pool=clean_db,
    ))


@pytest.mark.asyncio
async def test_lascia_toglie_subito_e_senza_saldo_non_scrive(r):
    await r.lev.add_coins(G, 1, 100)
    assert await r.las.lascia(G, 2, 10) is None
    assert await r.las.lascia(G, 1, 101) is None
    assert (await r.lev.get_totals(G, 1)).coins_total == 100
    assert await r.las.lascia(G, 1, 40) is not None
    assert (await r.lev.get_totals(G, 1)).coins_total == 60
    for brutto in (0, -5, 1_000_001):
        with pytest.raises(ValueError):
            await r.las.lascia(G, 1, brutto)


@pytest.mark.asyncio
async def test_le_prende_uno_solo_anche_con_clic_insieme_e_non_chi_le_ha_lasciate(r):
    await r.lev.add_coins(G, 1, 100)
    lid = await r.las.lascia(G, 1, 100)
    assert await r.las.prendi(lid, G, 1) is None  # non le proprie
    assert await r.las.prendi(lid, G + 1, 2) is None  # non da un altro server
    await apri_connessioni(r.pool, 5)
    esiti = await asyncio.gather(*[r.las.prendi(lid, G, u) for u in range(2, 7)])
    assert [e for e in esiti if e] == [100]
    totale = sum([(await r.lev.get_totals(G, u)).coins_total for u in range(1, 7)])
    assert totale == 100  # niente creato, niente perso
    assert await r.las.rimborsa_scaduti() == 0


@pytest.mark.asyncio
async def test_rimborso_dei_scaduti_una_volta_sola_e_dopo_non_si_prende(r):
    await r.lev.add_coins(G, 1, 50)
    lid = await r.las.lascia(G, 1, 50)
    await r.pool.execute("UPDATE economia_lasciti SET scade_at = now() - interval '1 second'")
    assert await r.las.prendi(lid, G, 2) is None  # scaduto
    await apri_connessioni(r.pool, 3)
    n = await asyncio.gather(*[r.las.rimborsa_scaduti() for _ in range(3)])
    assert sum(n) == 1
    assert (await r.lev.get_totals(G, 1)).coins_total == 50
    assert await r.las.prendi(lid, G, 2) is None


@pytest.mark.asyncio
async def test_impostazioni_drop_e_limiti(r):
    for brutto in ({"drop_per_mille": 101}, {"drop_min": 0}, {"drop_pausa": 3601}, {"drop_min": 90, "drop_max": 10}):
        with pytest.raises(ValueError):
            await r.imp.set_options(G, **brutto)
    await r.imp.set_options(G, drop_per_mille=0, drop_min=5, drop_max=7)
    i = (await r.imp.get_config(G, fresco=True)).impostazioni
    assert (i.drop_per_mille, i.drop_min, i.drop_max, i.drop_canale_id) == (0, 5, 7, None)


def _messaggio(canale_id=7):
    m = MagicMock()
    m.guild = fake_guild(G)
    m.channel = MagicMock(id=canale_id, parent=None, parent_id=None, category_id=None)
    m.channel.send = AsyncMock()
    return m


@pytest.fixture
async def livelli(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, G)
    c = LevelingCog(bot=None)
    c.cog_unload()
    yield c
    leveling_settings_repo._cache.clear()


@pytest.mark.asyncio
async def test_drop_spento_canale_giusto_e_pausa(livelli, monkeypatch):
    import cogs.leveling.leveling as modulo
    monkeypatch.setattr(modulo.random, "random", lambda: 0.0)  # tira sempre «sì»
    from core.leveling_logic import LevelingSettings
    m = _messaggio()
    await livelli._drop_casuale(m, LevelingSettings(drop_per_mille=0))
    m.channel.send.assert_not_awaited()
    await livelli._drop_casuale(m, LevelingSettings(drop_per_mille=10, drop_canale_id=99))
    m.channel.send.assert_not_awaited()
    imp = LevelingSettings(drop_per_mille=10, drop_canale_id=7, drop_min=20, drop_max=20, drop_pausa=600)
    await livelli._drop_casuale(m, imp)
    assert m.channel.send.await_count == 1 and "20" in m.channel.send.await_args.args[0]
    await livelli._drop_casuale(m, imp)  # in pausa
    assert m.channel.send.await_count == 1


@pytest.mark.asyncio
async def test_comando_lascia_e_forziere(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, G)
    cog = DropCog(bot=MagicMock())
    cog.cog_unload()
    lev = LevelingRepository(pool_provider=lambda: clean_db)
    await lev.add_coins(G, 1, 30)
    i = fake_interaction(guild=fake_guild(G), user=fake_member(1))
    i.channel = MagicMock()
    i.channel.permissions_for.return_value.send_messages = True
    await cog.lascia.callback(cog, i, 20)
    assert (await lev.get_totals(G, 1)).coins_total == 10
    assert i.response.send_message.await_args.kwargs["view"] is not None
    i2 = fake_interaction(guild=fake_guild(G), user=fake_member(1))
    i2.channel = i.channel
    await cog.lascia.callback(cog, i2, 20)  # saldo non basta
    assert (await lev.get_totals(G, 1)).coins_total == 10
    assert i2.response.send_message.await_args.kwargs.get("ephemeral") is True
