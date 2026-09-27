"""
tests/test_restore_retention_listeners.py
=============================================
Test dei listener on_member_ban/on_member_remove/on_member_join di
RestoreCog (SPEC.md §11.11) — retention dei token OAuth salvati.
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from cogs.utility.restore import RestoreCog
from core.database import Database
from core.oauth_crypto import generate_key
from core.repositories.restore_oauth_repo import (
    STATUS_ACTIVE,
    STATUS_BANNED_BLACKLISTED,
    STATUS_KICKED_FLAGGED,
    RestoreOAuthRepository,
)

CHIAVE_TEST = generate_key()


class _FakeAuditEntry:
    def __init__(self, target_id: int, created_at: datetime) -> None:
        self.target_id = target_id
        self.created_at = created_at


class _FakeAuditLogIterator:
    def __init__(self, voci: list[_FakeAuditEntry]) -> None:
        self._voci = voci

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for voce in self._voci:
            yield voce


class _FakeGuild:
    def __init__(self, guild_id: int, voci_kick: list[_FakeAuditEntry] | None = None, canale=None) -> None:
        self.id = guild_id
        self._voci_kick = voci_kick or []
        self._canale = canale

    def audit_logs(self, limit=5, action=None):
        return _FakeAuditLogIterator(self._voci_kick)

    def get_channel(self, channel_id: int):
        return self._canale


class _FakeMember:
    def __init__(self, member_id: int, guild: _FakeGuild) -> None:
        self.id = member_id
        self.guild = guild
        self.mention = f"<@{member_id}>"


class _FakeChannel:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send(self, content: str) -> None:
        self.sent_messages.append(content)


@pytest.fixture
async def database():
    db_instance = Database()
    await db_instance.connect()
    await db_instance.run_migrations()
    yield db_instance
    await db_instance.pool.execute("DELETE FROM restore_oauth_tokens")
    await db_instance.pool.execute("DELETE FROM guild_config")
    await db_instance.close()


def _patch_oauth_repo(monkeypatch, database):
    import cogs.utility.restore as restore_module

    repo = RestoreOAuthRepository(
        pool_provider=lambda: database.pool, encryption_key_provider=lambda: CHIAVE_TEST
    )
    monkeypatch.setattr(restore_module, "restore_oauth_repo", repo)
    return repo


@pytest.mark.asyncio
async def test_on_member_ban_marca_il_token_come_bannato(database, monkeypatch):
    repo = _patch_oauth_repo(monkeypatch, database)
    await repo.save_token(100, 1, "a", "r", datetime.now(timezone.utc) + timedelta(days=7))

    cog = RestoreCog(bot=None)
    await cog.on_member_ban(_FakeGuild(100), _FakeMember(1, _FakeGuild(100)))

    token = await repo.get_token(100, 1)
    assert token.status == STATUS_BANNED_BLACKLISTED


@pytest.mark.asyncio
async def test_on_member_ban_senza_token_salvato_non_solleva(database, monkeypatch):
    _patch_oauth_repo(monkeypatch, database)
    cog = RestoreCog(bot=None)

    await cog.on_member_ban(_FakeGuild(100), _FakeMember(999, _FakeGuild(100)))  # non deve sollevare


@pytest.mark.asyncio
async def test_on_member_remove_con_voce_di_kick_recente_marca_kickato(database, monkeypatch):
    repo = _patch_oauth_repo(monkeypatch, database)
    await repo.save_token(100, 1, "a", "r", datetime.now(timezone.utc) + timedelta(days=7))

    ora = datetime.now(timezone.utc)
    guild = _FakeGuild(100, voci_kick=[_FakeAuditEntry(target_id=1, created_at=ora - timedelta(seconds=1))])
    member = _FakeMember(1, guild)

    cog = RestoreCog(bot=None)
    await cog.on_member_remove(member)

    token = await repo.get_token(100, 1)
    assert token.status == STATUS_KICKED_FLAGGED


@pytest.mark.asyncio
async def test_on_member_remove_senza_voce_di_kick_marca_uscita_spontanea(database, monkeypatch):
    repo = _patch_oauth_repo(monkeypatch, database)
    await repo.save_token(100, 1, "a", "r", datetime.now(timezone.utc) + timedelta(days=7))

    guild = _FakeGuild(100, voci_kick=[])
    member = _FakeMember(1, guild)

    cog = RestoreCog(bot=None)
    await cog.on_member_remove(member)

    token = await repo.get_token(100, 1)
    assert token.status == STATUS_ACTIVE
    assert token.left_at is not None


@pytest.mark.asyncio
async def test_on_member_join_di_un_kickato_flaggato_avvisa_il_canale_log(database, monkeypatch):
    repo = _patch_oauth_repo(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)

    await repo.save_token(100, 1, "a", "r", datetime.now(timezone.utc) + timedelta(days=7))
    await repo.mark_kicked(100, 1)
    await database.set_guild_setting(100, "mod_log_channel_id", 555)

    canale = _FakeChannel()
    guild = _FakeGuild(100, canale=canale)
    member = _FakeMember(1, guild)

    cog = RestoreCog(bot=None)
    await cog.on_member_join(member)

    assert len(canale.sent_messages) == 1
    assert "kickato" in canale.sent_messages[0]


@pytest.mark.asyncio
async def test_on_member_join_senza_token_flaggato_non_avvisa(database, monkeypatch):
    repo = _patch_oauth_repo(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)

    canale = _FakeChannel()
    guild = _FakeGuild(100, canale=canale)
    member = _FakeMember(1, guild)

    cog = RestoreCog(bot=None)
    await cog.on_member_join(member)  # nessun token affatto

    assert canale.sent_messages == []
