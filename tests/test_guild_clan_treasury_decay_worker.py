"""
tests/test_guild_clan_treasury_decay_worker.py
===================================================
Test di GuildClanTreasuryDecayWorker.tick() contro PostgreSQL reale.
"""

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from core.database import Database
from core.guild_clan_treasury_decay_worker import GuildClanTreasuryDecayWorker
from core.repositories.guild_chest_repo import GuildChestRepository
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
    await database.pool.execute("DELETE FROM guild_chest_ledger")
    await database.pool.execute("DELETE FROM guild_chest")

    clan_repo = GuildClanRepository(pool_provider=lambda: database.pool)
    chest_repo = GuildChestRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(modulo, "guild_clan_repo", clan_repo)
    monkeypatch.setattr(modulo, "guild_chest_repo", chest_repo)

    yield clan_repo, chest_repo
    await database.pool.execute("DELETE FROM clan_treasury_ledger")
    await database.pool.execute("DELETE FROM clan_members")
    await database.pool.execute("DELETE FROM clans")
    await database.pool.execute("DELETE FROM guild_chest_ledger")
    await database.pool.execute("DELETE FROM guild_chest")
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
    clan_repo, chest_repo = repo
    clan_id = await _crea_ufficializzato(clan_repo)
    await clan_repo.donate(clan_id, user_id=1, amount=115_000)  # saldo: 100.000

    await GuildClanTreasuryDecayWorker().tick(now=ORA)

    clan = await clan_repo.get_clan(clan_id)
    assert clan.treasury_balance == 90_000
    assert clan.last_decay_period == "2026-10"


@pytest.mark.asyncio
async def test_clan_non_ufficializzato_non_viene_toccato(repo):
    clan_repo, chest_repo = repo
    clan_id = await clan_repo.create_clan(
        100, tag="ABC", name="Clan", owner_id=1,
        officialize_deadline=ORA + timedelta(hours=24),
    )
    # non ufficializzato

    await GuildClanTreasuryDecayWorker().tick(now=ORA)

    assert (await clan_repo.get_clan(clan_id)).treasury_balance == -15_000  # invariato


@pytest.mark.asyncio
async def test_secondo_tick_nello_stesso_mese_non_decade_due_volte(repo):
    clan_repo, chest_repo = repo
    clan_id = await _crea_ufficializzato(clan_repo)
    await clan_repo.donate(clan_id, user_id=1, amount=115_000)  # saldo: 100.000

    worker = GuildClanTreasuryDecayWorker()
    await worker.tick(now=ORA)
    await worker.tick(now=ORA)  # secondo tick, stesso mese

    assert (await clan_repo.get_clan(clan_id)).treasury_balance == 90_000  # decaduto una sola volta


@pytest.mark.asyncio
async def test_decadimento_mensile_confluisce_nella_cassa_di_server(repo):
    clan_repo, chest_repo = repo
    clan_id = await _crea_ufficializzato(clan_repo, guild_id=777)
    await clan_repo.donate(clan_id, user_id=1, amount=115_000)  # saldo: 100.000

    await GuildClanTreasuryDecayWorker().tick(now=ORA)

    # 10% di 100.000 decaduto -> 10.000 nella cassa del server 777
    assert await chest_repo.get_balance(777) == 10_000


@pytest.mark.asyncio
async def test_decadimento_a_saldo_zero_non_deposita_nulla_in_cassa(repo):
    clan_repo, chest_repo = repo
    clan_id = await _crea_ufficializzato(clan_repo, guild_id=778)
    # nessuna donazione: la tesoreria resta al deficit di creazione (negativo),
    # apply_monthly_treasury_decay non decade un saldo <= 0

    await GuildClanTreasuryDecayWorker().tick(now=ORA)

    assert await chest_repo.get_balance(778) == 0


@pytest.mark.asyncio
async def test_delta_in_cassa_usa_il_saldo_reale_non_quello_stale_della_lista(repo, monkeypatch):
    """
    Regressione per il bug del delta "stale": prima del fix, il worker
    calcolava il delta da versare in cassa come
    `clan.treasury_balance - nuovo_saldo`, dove `clan.treasury_balance`
    proveniva da `list_officialized_clans()` (lettura NON sotto lock).
    Se tra quella lista e il lock (`apply_monthly_decay`, FOR UPDATE)
    il saldo reale del clan cambia — es. una donazione arrivata nel
    frattempo — quel delta risultava sbagliato.

    Qui simuliamo esattamente questo scenario: il worker riceve dalla
    lista un `Clan` con un `treasury_balance` "vecchio" (1), mentre il
    saldo REALE su database è 100.000. Dopo il fix, il worker calcola
    il delta da (saldo_prima, saldo_dopo) restituiti da
    apply_monthly_decay — cioè dal saldo REALE letto sotto lock — non
    dal valore stale della lista.
    """
    clan_repo, chest_repo = repo
    clan_id = await _crea_ufficializzato(clan_repo, guild_id=888)
    await clan_repo.donate(clan_id, user_id=1, amount=115_000)  # saldo reale: 100.000

    clan_reale = await clan_repo.get_clan(clan_id)
    clan_stale = dataclasses.replace(clan_reale, treasury_balance=1)

    async def _lista_stale():
        return [clan_stale]

    monkeypatch.setattr(clan_repo, "list_officialized_clans", _lista_stale)

    await GuildClanTreasuryDecayWorker().tick(now=ORA)

    # 10% di 100.000 (saldo reale, non del valore stale=1 della lista)
    # deve confluire nella cassa del server 888.
    assert await chest_repo.get_balance(888) == 10_000
    assert (await clan_repo.get_clan(clan_id)).treasury_balance == 90_000
