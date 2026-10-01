"""
tests/test_backup_snapshot_worker.py
========================================
Test di BackupSnapshotWorker.tick() contro PostgreSQL reale — con
oggetti finti minimi per guild/membri (nessuna vera connessione a
Discord necessaria).
"""

import pytest

from core.backup_snapshot_worker import BackupSnapshotWorker
from core.database import Database
from core.repositories.backup_repo import BackupRepository
from core.repositories.backup_user_snapshot_repo import BackupUserSnapshotRepository
from core.repositories.verify_repo import VerifyRepository


class _FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id


class _FakeAvatar:
    url = "https://cdn.example/avatar.png"


class _FakeMember:
    def __init__(self, member_id: int, name: str, bot: bool = False, role_ids: list[int] | None = None) -> None:
        self.id = member_id
        self._name = name
        self.bot = bot
        self.roles = [_FakeRole(r) for r in (role_ids or [])]
        self.display_avatar = _FakeAvatar()

    def __str__(self) -> str:
        return self._name


class _FakeGuild:
    def __init__(self, guild_id: int, members: list[_FakeMember]) -> None:
        self.id = guild_id
        self.members = members


class _FakeMainBot:
    def __init__(self, guilds_by_id: dict) -> None:
        self._guilds_by_id = guilds_by_id

    def get_guild(self, guild_id: int):
        return self._guilds_by_id.get(guild_id)


@pytest.fixture
async def repos():
    database = Database()
    await database.connect()
    await database.run_migrations()
    backup_repo_test = BackupRepository(pool_provider=lambda: database.pool)
    snapshot_repo_test = BackupUserSnapshotRepository(pool_provider=lambda: database.pool)
    verify_repo_test = VerifyRepository(pool_provider=lambda: database.pool)
    yield backup_repo_test, snapshot_repo_test, verify_repo_test
    await database.pool.execute("DELETE FROM backup_pairs")
    await database.pool.execute("DELETE FROM backup_user_snapshots")
    await database.pool.execute("DELETE FROM verify_config")
    await database.close()


@pytest.mark.asyncio
async def test_tick_fotografa_solo_i_verificati_non_bot(repos, monkeypatch):
    backup_repo_test, snapshot_repo_test, verify_repo_test = repos
    import core.backup_snapshot_worker as worker_module

    monkeypatch.setattr(worker_module, "backup_repo", backup_repo_test)
    monkeypatch.setattr(worker_module, "backup_user_snapshot_repo", snapshot_repo_test)
    monkeypatch.setattr(worker_module, "verify_repo", verify_repo_test)

    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)
    await verify_repo_test.set_config(
        guild_id=100,
        method="button",
        verified_role_id=1,
        min_account_age_days=0,
        min_mutual_servers=0,
        captcha_enabled=False,
        log_channel_id=None,
    )

    membri = [
        _FakeMember(1, "Verificato", role_ids=[1]),
        _FakeMember(2, "NonVerificato", role_ids=[]),
        _FakeMember(3, "UnBot", bot=True, role_ids=[1]),
    ]
    main_bot = _FakeMainBot({100: _FakeGuild(100, membri)})

    worker = BackupSnapshotWorker()
    await worker.tick(main_bot)

    snapshot = await snapshot_repo_test.get_snapshot(100)
    assert {e.user_id for e in snapshot} == {1}


@pytest.mark.asyncio
async def test_tick_senza_verify_configurato_include_tutti_i_non_bot(repos, monkeypatch):
    backup_repo_test, snapshot_repo_test, verify_repo_test = repos
    import core.backup_snapshot_worker as worker_module

    monkeypatch.setattr(worker_module, "backup_repo", backup_repo_test)
    monkeypatch.setattr(worker_module, "backup_user_snapshot_repo", snapshot_repo_test)
    monkeypatch.setattr(worker_module, "verify_repo", verify_repo_test)

    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)

    membri = [_FakeMember(1, "Utente1"), _FakeMember(2, "Utente2"), _FakeMember(3, "Bot", bot=True)]
    main_bot = _FakeMainBot({100: _FakeGuild(100, membri)})

    worker = BackupSnapshotWorker()
    await worker.tick(main_bot)

    snapshot = await snapshot_repo_test.get_snapshot(100)
    assert {e.user_id for e in snapshot} == {1, 2}


@pytest.mark.asyncio
async def test_tick_ignora_i_main_senza_backup_attivo(repos, monkeypatch):
    backup_repo_test, snapshot_repo_test, verify_repo_test = repos
    import core.backup_snapshot_worker as worker_module

    monkeypatch.setattr(worker_module, "backup_repo", backup_repo_test)
    monkeypatch.setattr(worker_module, "backup_user_snapshot_repo", snapshot_repo_test)
    monkeypatch.setattr(worker_module, "verify_repo", verify_repo_test)

    await backup_repo_test.define_main(100)  # nessun backup ancora

    main_bot = _FakeMainBot({100: _FakeGuild(100, [_FakeMember(1, "Utente")])})

    worker = BackupSnapshotWorker()
    await worker.tick(main_bot)

    assert await snapshot_repo_test.get_snapshot(100) == []


@pytest.mark.asyncio
async def test_tick_server_non_raggiungibile_non_solleva(repos, monkeypatch):
    backup_repo_test, snapshot_repo_test, verify_repo_test = repos
    import core.backup_snapshot_worker as worker_module

    monkeypatch.setattr(worker_module, "backup_repo", backup_repo_test)
    monkeypatch.setattr(worker_module, "backup_user_snapshot_repo", snapshot_repo_test)
    monkeypatch.setattr(worker_module, "verify_repo", verify_repo_test)

    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)

    main_bot = _FakeMainBot({})  # main NON risulta in nessun guild

    worker = BackupSnapshotWorker()
    await worker.tick(main_bot)  # non deve sollevare

    assert await snapshot_repo_test.get_snapshot(100) == []


@pytest.mark.asyncio
async def test_start_aspetta_che_il_bot_sia_pronto_prima_del_primo_tick(monkeypatch):
    """Il primo giro non deve partire prima del login (guild vuote = 0 utenti)."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    pronto = asyncio.Event()
    bot = MagicMock()
    bot.wait_until_ready = pronto.wait

    worker = BackupSnapshotWorker()
    tick = AsyncMock()
    monkeypatch.setattr(worker, "tick", tick)

    worker.start(bot)
    try:
        await asyncio.sleep(0.05)
        tick.assert_not_awaited()  # bot non ancora pronto

        pronto.set()
        await asyncio.sleep(0.05)
        tick.assert_awaited_once()
    finally:
        worker.stop()
