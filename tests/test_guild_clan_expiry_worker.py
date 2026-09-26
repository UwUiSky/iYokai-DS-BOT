"""
tests/test_guild_clan_expiry_worker.py
==========================================
Test di GuildClanExpiryWorker.tick() contro PostgreSQL reale — clan
non ufficializzati la cui finestra di 24h è scaduta vengono
eliminati, insieme alla categoria/canali Discord se esistono ancora.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.database import Database
from core.guild_clan_expiry_worker import GuildClanExpiryWorker
from core.repositories.guild_clan_repo import GuildClanRepository

ORA = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.deleted = False

    async def delete(self, reason: str | None = None) -> None:
        self.deleted = True


class _FakeCategory:
    def __init__(self, category_id: int, channels: list) -> None:
        self.id = category_id
        self.channels = channels
        self.deleted = False

    async def delete(self, reason: str | None = None) -> None:
        self.deleted = True


class _FakeGuild:
    def __init__(self, guild_id: int, channels_by_id: dict) -> None:
        self.id = guild_id
        self._channels_by_id = channels_by_id

    def get_channel(self, channel_id: int):
        return self._channels_by_id.get(channel_id)


class _FakeBot:
    def __init__(self, guilds: list) -> None:
        self._guilds_by_id = {g.id: g for g in guilds}

    def get_guild(self, guild_id: int):
        return self._guilds_by_id.get(guild_id)


@pytest.fixture
async def repo(monkeypatch):
    import core.guild_clan_expiry_worker as modulo

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


async def _crea_non_ufficializzato(clan_repo, guild_id=100, tag="ABC", scadenza=None):
    return await clan_repo.create_clan(
        guild_id, tag=tag, name="Clan", owner_id=1,
        officialize_deadline=scadenza or (ORA - timedelta(hours=1)),  # già scaduta
    )


@pytest.mark.asyncio
async def test_elimina_un_clan_scaduto_non_ufficializzato(repo):
    clan_id = await _crea_non_ufficializzato(repo)

    await GuildClanExpiryWorker().tick(bot=_FakeBot([]), now=ORA)

    assert await repo.get_clan(clan_id) is None


@pytest.mark.asyncio
async def test_non_elimina_un_clan_non_ancora_scaduto(repo):
    clan_id = await _crea_non_ufficializzato(repo, scadenza=ORA + timedelta(hours=1))

    await GuildClanExpiryWorker().tick(bot=_FakeBot([]), now=ORA)

    assert await repo.get_clan(clan_id) is not None


@pytest.mark.asyncio
async def test_non_elimina_un_clan_gia_ufficializzato_anche_se_la_scadenza_e_passata(repo):
    clan_id = await _crea_non_ufficializzato(repo)
    await repo.set_officialized(clan_id)

    await GuildClanExpiryWorker().tick(bot=_FakeBot([]), now=ORA)

    assert await repo.get_clan(clan_id) is not None


@pytest.mark.asyncio
async def test_elimina_anche_categoria_e_canali_discord(repo):
    clan_id = await _crea_non_ufficializzato(repo, guild_id=200)
    canale = _FakeChannel(111)
    categoria = _FakeCategory(50, [canale])
    guild = _FakeGuild(200, {50: categoria})
    await repo.set_category_id(clan_id, categoria.id)

    await GuildClanExpiryWorker().tick(bot=_FakeBot([guild]), now=ORA)

    assert canale.deleted is True
    assert categoria.deleted is True
    assert await repo.get_clan(clan_id) is None


@pytest.mark.asyncio
async def test_guild_non_trovata_elimina_comunque_il_record(repo):
    clan_id = await _crea_non_ufficializzato(repo, guild_id=999)

    await GuildClanExpiryWorker().tick(bot=_FakeBot([]), now=ORA)  # guild 999 non nel bot

    assert await repo.get_clan(clan_id) is None
