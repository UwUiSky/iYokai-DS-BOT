"""
tests/test_guild_clan_treasury_decay_worker.py
===================================================
Test di GuildClanTreasuryDecayWorker.tick() contro PostgreSQL reale.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.database import Database
from core.guild_clan_treasury_decay_worker import GuildClanTreasuryDecayWorker
from core.repositories.guild_clan_repo import GuildClanRepository

ORA = datetime(2026, 10, 1, 0, 30, tzinfo=timezone.utc)  # periodo corrente: 2026-10


@pytest.fixture
async def repo(monkeypatch):
    import core.guild_clan_treasury_decay_worker as modulo

    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM clan_treasury_ledger")
    await database.pool.execute("DELETE FROM clan_members")
    await database.pool.execute("DELETE FROM clans")

    clan_repo = GuildClanRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(modulo, "guild_clan_repo", clan_repo)

    yield clan_repo
    await database.pool.execute("DELETE FROM clan_treasury_ledger")
    await database.pool.execute("DELETE FROM clan_members")
    await database.pool.execute("DELETE FROM clans")
    await database.close()


async def _crea_ufficializzato(clan_repo, guild_id=100, tag="ABC"):
    clan_id = await clan_repo.create_clan(
        guild_id, tag=tag, name="Clan", owner_id=1,
        officialize_deadline=ORA + timedelta(hours=24),
    )
    await clan_repo.set_officialized(clan_id)
    return clan_id


@pytest.mark.asyncio
async def test_decade_la_tesoreria_di_un_clan_ufficializzato(repo):
    clan_id = await _crea_ufficializzato(repo)
    await repo.donate(clan_id, user_id=1, amount=115_000)  # saldo: 100.000

    await GuildClanTreasuryDecayWorker().tick(now=ORA)

    clan = await repo.get_clan(clan_id)
    assert clan.treasury_balance == 90_000
    assert clan.last_decay_period == "2026-10"


@pytest.mark.asyncio
async def test_clan_non_ufficializzato_non_viene_toccato(repo):
    clan_id = await repo.create_clan(
        100, tag="ABC", name="Clan", owner_id=1,
        officialize_deadline=ORA + timedelta(hours=24),
    )
    # non ufficializzato

    await GuildClanTreasuryDecayWorker().tick(now=ORA)

    assert (await repo.get_clan(clan_id)).treasury_balance == -15_000  # invariato


@pytest.mark.asyncio
async def test_secondo_tick_nello_stesso_mese_non_decade_due_volte(repo):
    clan_id = await _crea_ufficializzato(repo)
    await repo.donate(clan_id, user_id=1, amount=115_000)  # saldo: 100.000

    worker = GuildClanTreasuryDecayWorker()
    await worker.tick(now=ORA)
    await worker.tick(now=ORA)  # secondo tick, stesso mese

    assert (await repo.get_clan(clan_id)).treasury_balance == 90_000  # decaduto una sola volta
