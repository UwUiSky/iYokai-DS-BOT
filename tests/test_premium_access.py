"""
tests/test_premium_access.py
================================
Test di core.premium.guild_has_premium_access — i quattro meccanismi
di sblocco attivi oggi (SPEC.md §3.1): override ALPHA, whitelist,
premium via cassa (già testato altrove, qui solo l'integrazione),
nitro boost sul server principale, abbonamento mensile/annuale per
modulo.
"""

from datetime import datetime, timedelta, timezone

import pytest

import core.premium as premium_module
from core.database import Database
from core.repositories.module_subscription_repo import ModuleSubscriptionRepository


class _ConfigFinta:
    def __init__(self, alpha_unlock_all: bool = False, main_guild_id: int = 999) -> None:
        self.PREMIUM_ALPHA_UNLOCK_ALL = alpha_unlock_all
        self.MAIN_GUILD_ID = main_guild_id


class _FakeMember:
    def __init__(self, premium_since=None) -> None:
        self.premium_since = premium_since


class _FakeGuild:
    def __init__(self, guild_id: int, owner_id: int | None = None, members: dict | None = None) -> None:
        self.id = guild_id
        self.owner_id = owner_id
        self._members = members or {}

    def get_member(self, user_id: int):
        return self._members.get(user_id)


class _FakeBot:
    def __init__(self, guilds: dict) -> None:
        self._guilds = guilds

    def get_guild(self, guild_id: int):
        return self._guilds.get(guild_id)


@pytest.fixture
async def database(monkeypatch):
    db = Database()
    await db.connect()
    await db.run_migrations()
    # Pulizia ANCHE all'inizio, non solo alla fine: altri file di test
    # (es. test_module_subscription_repo.py) scrivono righe per lo
    # stesso guild_id=100 di comodo usato qui, e senza questo la
    # prima esecuzione di questo file può trovare stato residuo da
    # un'esecuzione precedente della suite.
    await db.pool.execute("DELETE FROM premium_whitelist")
    await db.pool.execute("DELETE FROM guild_premium_status")
    await db.pool.execute("DELETE FROM module_subscriptions")

    from core.database import db as real_db_singleton
    original_pool = real_db_singleton._pool
    real_db_singleton._pool = db.pool

    monkeypatch.setattr(premium_module, "config", _ConfigFinta())

    yield db

    real_db_singleton._pool = original_pool
    await db.pool.execute("DELETE FROM premium_whitelist")
    await db.pool.execute("DELETE FROM guild_premium_status")
    await db.pool.execute("DELETE FROM module_subscriptions")
    await db.close()


@pytest.mark.asyncio
async def test_alpha_override_sblocca_sempre_tutto(monkeypatch):
    monkeypatch.setattr(premium_module, "config", _ConfigFinta(alpha_unlock_all=True))

    assert await premium_module.guild_has_premium_access(1, "qualunque_modulo") is True


@pytest.mark.asyncio
async def test_senza_nessuna_condizione_non_ha_accesso(database):
    assert await premium_module.guild_has_premium_access(100, "spam_trap") is False


@pytest.mark.asyncio
async def test_whitelist_sblocca_tutto(database):
    await database.add_guild_to_whitelist(100, added_by=1, reason="test")

    assert await premium_module.guild_has_premium_access(100, "spam_trap") is True
    assert await premium_module.guild_has_premium_access(100, "un_altro_modulo") is True


@pytest.mark.asyncio
async def test_nitro_boost_owner_del_server_sblocca_tutto(database):
    owner_id = 42
    main_guild = _FakeGuild(999, members={owner_id: _FakeMember(premium_since=datetime.now(timezone.utc))})
    server_richiedente = _FakeGuild(100, owner_id=owner_id)
    bot = _FakeBot({999: main_guild, 100: server_richiedente})

    ha_accesso = await premium_module.guild_has_premium_access(100, "spam_trap", bot=bot)

    assert ha_accesso is True


@pytest.mark.asyncio
async def test_owner_senza_boost_non_sblocca(database):
    owner_id = 42
    main_guild = _FakeGuild(999, members={owner_id: _FakeMember(premium_since=None)})
    server_richiedente = _FakeGuild(100, owner_id=owner_id)
    bot = _FakeBot({999: main_guild, 100: server_richiedente})

    assert await premium_module.guild_has_premium_access(100, "spam_trap", bot=bot) is False


@pytest.mark.asyncio
async def test_owner_non_presente_sul_server_principale_non_sblocca(database):
    main_guild = _FakeGuild(999, members={})  # l'owner non è mai entrato lì
    server_richiedente = _FakeGuild(100, owner_id=42)
    bot = _FakeBot({999: main_guild, 100: server_richiedente})

    assert await premium_module.guild_has_premium_access(100, "spam_trap", bot=bot) is False


@pytest.mark.asyncio
async def test_senza_bot_il_controllo_nitro_boost_non_si_applica_ma_non_solleva(database):
    # Nessun bot passato (es. un worker che non lo fa ancora): il
    # controllo nitro boost va saltato in silenzio, mai un crash.
    assert await premium_module.guild_has_premium_access(100, "spam_trap", bot=None) is False


@pytest.mark.asyncio
async def test_abbonamento_mensile_sblocca_solo_il_modulo_specifico(database):
    sub_repo = ModuleSubscriptionRepository(pool_provider=lambda: database.pool)
    await sub_repo.grant(100, "spam_trap", duration_days=30)

    assert await premium_module.guild_has_premium_access(100, "spam_trap") is True
    assert await premium_module.guild_has_premium_access(100, "automod") is False


@pytest.mark.asyncio
async def test_abbonamento_scaduto_non_sblocca(database):
    sub_repo = ModuleSubscriptionRepository(pool_provider=lambda: database.pool)
    ieri = datetime.now(timezone.utc) - timedelta(days=1)
    await sub_repo.grant(100, "spam_trap", duration_days=30, now=ieri - timedelta(days=30))

    assert await premium_module.guild_has_premium_access(100, "spam_trap") is False
