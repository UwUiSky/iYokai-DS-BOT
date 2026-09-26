"""
tests/test_weekly_personal_decay_worker.py
==============================================
Test di WeeklyPersonalDecayWorker.tick() contro PostgreSQL reale
(SPEC.md §15.15 — decadimento settimanale del 10% sui coin
personali di QUALUNQUE membro, in un clan o no, con le coin decadute
che confluiscono nella cassa del server).
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.database import Database
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository
from core.weekly_personal_decay_worker import WeeklyPersonalDecayWorker

# 2026-09-24 è un giovedì della settimana ISO 2026-W39
ORA = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def repos(monkeypatch):
    import core.weekly_personal_decay_worker as modulo

    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM leveling_totals")
    await database.pool.execute("DELETE FROM leveling_activity")
    await database.pool.execute("DELETE FROM guild_chest_ledger")
    await database.pool.execute("DELETE FROM guild_chest")

    leveling_repo = LevelingRepository(pool_provider=lambda: database.pool)
    chest_repo = GuildChestRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(modulo, "leveling_repo", leveling_repo)
    monkeypatch.setattr(modulo, "guild_chest_repo", chest_repo)

    yield leveling_repo, chest_repo
    await database.pool.execute("DELETE FROM leveling_totals")
    await database.pool.execute("DELETE FROM leveling_activity")
    await database.pool.execute("DELETE FROM guild_chest_ledger")
    await database.pool.execute("DELETE FROM guild_chest")
    await database.close()


@pytest.mark.asyncio
async def test_decade_il_saldo_personale_di_chiunque_ha_coin(repos):
    leveling_repo, chest_repo = repos
    await leveling_repo.add_coins(100, 1, 500)

    await WeeklyPersonalDecayWorker().tick(now=ORA)

    assert (await leveling_repo.get_totals(100, 1)).coins_total == 450


@pytest.mark.asyncio
async def test_decade_anche_chi_non_e_in_nessun_clan(repos):
    # Nessuna tabella clan coinvolta qui: il worker legge solo
    # leveling_totals, quindi "in un clan o no" è già garantito dal
    # fatto che non fa nessuna join con clan_members.
    leveling_repo, chest_repo = repos
    await leveling_repo.add_coins(555, 42, 1_000)

    await WeeklyPersonalDecayWorker().tick(now=ORA)

    assert (await leveling_repo.get_totals(555, 42)).coins_total == 900


@pytest.mark.asyncio
async def test_le_coin_decadute_confluiscono_nella_cassa_del_server(repos):
    leveling_repo, chest_repo = repos
    await leveling_repo.add_coins(100, 1, 500)

    await WeeklyPersonalDecayWorker().tick(now=ORA)

    assert await chest_repo.get_balance(100) == 50


@pytest.mark.asyncio
async def test_non_decade_due_volte_nella_stessa_settimana(repos):
    leveling_repo, chest_repo = repos
    await leveling_repo.add_coins(100, 1, 500)

    worker = WeeklyPersonalDecayWorker()
    await worker.tick(now=ORA)
    await worker.tick(now=ORA)  # secondo tick, stessa settimana

    assert (await leveling_repo.get_totals(100, 1)).coins_total == 450
    assert await chest_repo.get_balance(100) == 50


@pytest.mark.asyncio
async def test_decade_di_nuovo_alla_settimana_successiva(repos):
    leveling_repo, chest_repo = repos
    await leveling_repo.add_coins(100, 1, 500)

    worker = WeeklyPersonalDecayWorker()
    await worker.tick(now=ORA)
    settimana_dopo = ORA + timedelta(days=7)
    await worker.tick(now=settimana_dopo)

    assert (await leveling_repo.get_totals(100, 1)).coins_total == 405  # 450 -> 405
    assert await chest_repo.get_balance(100) == 95  # 50 + 45


@pytest.mark.asyncio
async def test_saldo_al_minimo_non_viene_toccato_e_non_deposita_in_cassa(repos):
    leveling_repo, chest_repo = repos
    await leveling_repo.add_coins(100, 1, 1)

    await WeeklyPersonalDecayWorker().tick(now=ORA)

    assert (await leveling_repo.get_totals(100, 1)).coins_total == 1
    assert await chest_repo.get_balance(100) == 0


@pytest.mark.asyncio
async def test_piu_server_diversi_ognuno_con_la_propria_cassa(repos):
    leveling_repo, chest_repo = repos
    await leveling_repo.add_coins(100, 1, 500)
    await leveling_repo.add_coins(200, 2, 200)

    await WeeklyPersonalDecayWorker().tick(now=ORA)

    assert await chest_repo.get_balance(100) == 50
    assert await chest_repo.get_balance(200) == 20
