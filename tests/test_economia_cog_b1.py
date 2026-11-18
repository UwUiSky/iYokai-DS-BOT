"""
tests/test_economia_cog_b1.py
=============================
Comandi e ascoltatori di cogs/leveling/economia.py (#125 B1): ECO-002, 014, 010, 012, 023, 026.
Funzioni coperte: SPEC §15 (catalogo #125)
"""

from unittest.mock import AsyncMock

import pytest

from cogs.leveling.economia import EconomiaCog, righe_stato
from core.leveling_logic import LevelingSettings
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

G = 100


@pytest.fixture
async def cog(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, G)
    c = EconomiaCog(bot=None)
    yield c
    leveling_settings_repo._cache.clear() if hasattr(leveling_settings_repo._cache, "clear") else None


def _i(user_id=1, name="Server di test"):
    i = fake_interaction(guild=fake_guild(G, name), user=fake_member(user_id))
    i.permissions.manage_guild = True
    return i


def test_stato_elenca_tutte_le_regole():
    chiavi = [k for k, _ in righe_stato(LevelingSettings())]
    assert len(chiavi) == len(set(chiavi)) == 11


@pytest.mark.asyncio
async def test_ingresso_dà_il_saldo_una_volta_e_ai_bot_niente(cog, clean_db):
    await leveling_settings_repo.set_options(G, saldo_iniziale=25)
    m = fake_member(5)
    m.guild = fake_guild(G)
    await cog.on_member_join(m)
    await cog.on_member_join(m)
    assert (await leveling_repo.get_totals(G, 5)).coins_total == 25
    b = fake_member(6, bot=True)
    b.guild = fake_guild(G)
    await cog.on_member_join(b)
    assert (await leveling_repo.get_totals(G, 6)).coins_total == 0


@pytest.mark.asyncio
async def test_uscita_cancella_solo_se_scelto(cog, clean_db):
    await leveling_repo.add_coins(G, 7, 60)
    m = fake_member(7)
    m.guild = fake_guild(G)
    await cog.on_member_remove(m)
    assert (await leveling_repo.get_totals(G, 7)).coins_total == 60
    await leveling_settings_repo.set_options(G, saldo_uscita="cancella")
    await cog.on_member_remove(m)
    assert (await leveling_repo.get_totals(G, 7)).coins_total == 0


@pytest.mark.asyncio
async def test_premio_settimanale_spento_poi_acceso_poi_gia_preso(cog, clean_db):
    i = _i()
    await cog.settimanale.callback(cog, i)
    assert "eco_premio_spento" in str(i.response.send_message.await_args) or i.response.send_message.await_args.kwargs["ephemeral"]
    await leveling_settings_repo.set_options(G, settimanale_coins=70)
    i2 = _i()
    await cog.settimanale.callback(cog, i2)
    assert (await leveling_repo.get_totals(G, 1)).coins_total == 70
    i3 = _i()
    await cog.settimanale.callback(cog, i3)
    assert (await leveling_repo.get_totals(G, 1)).coins_total == 70
    assert i3.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_azzera_serve_il_nome_giusto(cog, clean_db):
    await leveling_repo.add_coins(G, 1, 40)
    i = _i(name="Casa")
    await cog.azzera.callback(cog, i, "sbagliato")
    assert (await leveling_repo.get_totals(G, 1)).coins_total == 40
    i2 = _i(name="Casa")
    i2.response.defer = AsyncMock()
    await cog.azzera.callback(cog, i2, "Casa")
    assert (await leveling_repo.get_totals(G, 1)).coins_total == 0


@pytest.mark.asyncio
async def test_ruolo_toglie_senza_bot_e_senza_negativi(cog, clean_db):
    await leveling_repo.add_coins(G, 1, 30)
    ruolo = AsyncMock()
    ruolo.members = [fake_member(1), fake_member(2), fake_member(3, bot=True)]
    scelta = AsyncMock()
    scelta.value = "togli"
    i = _i(9)
    await cog.ruolo.callback(cog, i, ruolo, scelta, 100)
    assert (await leveling_repo.get_totals(G, 1)).coins_total == 0
    scelta.value = "aggiungi"
    await cog.ruolo.callback(cog, _i(9), ruolo, scelta, 10)
    assert [(await leveling_repo.get_totals(G, u)).coins_total for u in (1, 2, 3)] == [10, 10, 0]
