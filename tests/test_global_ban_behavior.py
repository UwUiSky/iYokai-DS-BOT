"""
tests/test_global_ban_behavior.py
=====================================
Test di comportamento reale di propagate_ban() (SPEC.md §7.3) —
stesso schema di tests/test_anti_raid_behavior.py: un bot e dei
server discord.py finti contro un database Postgres reale, per
l'opt-in del modulo (che usa l'attivazione modulo generica già
esistente, `db.is_module_active_for_guild`).
"""

import discord
import pytest

import cogs.security.global_ban as global_ban_module
from cogs.security.global_ban import MODULE_GLOBAL_BAN, propagate_ban
from core.database import Database


class _FakeHTTPResponse:
    status = 403
    reason = "Forbidden"


class _FakeGuild:
    def __init__(self, guild_id: int, name: str, raise_forbidden: bool = False) -> None:
        self.id = guild_id
        self.name = name
        self.banned: list[int] = []
        self.raise_forbidden = raise_forbidden

    async def ban(self, obj, reason=None, delete_message_seconds=0) -> None:
        if self.raise_forbidden:
            raise discord.Forbidden(response=_FakeHTTPResponse(), message="Permessi insufficienti")
        self.banned.append(obj.id)


class _FakeBot:
    def __init__(self, guilds: list[_FakeGuild]) -> None:
        self.guilds = guilds


GUILD_SOURCE = 800000100
GUILD_TARGET_ADERENTE = 800000101
GUILD_TARGET_NON_ADERENTE = 800000102
USER_ID = 900000900


@pytest.fixture
async def contesto(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    for guild_id in (GUILD_SOURCE, GUILD_TARGET_ADERENTE, GUILD_TARGET_NON_ADERENTE):
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
    await database.pool.execute(
        "DELETE FROM global_ban_log WHERE source_guild_id = $1", GUILD_SOURCE
    )

    monkeypatch.setattr(global_ban_module, "db", database)

    from core.database import db as real_db_singleton

    original_pool = real_db_singleton._pool
    real_db_singleton._pool = database.pool

    from core.repositories.global_ban_repo import global_ban_repo

    original_provider = global_ban_repo._pool_provider
    global_ban_repo._pool_provider = lambda: database.pool

    yield database

    global_ban_repo._pool_provider = original_provider
    real_db_singleton._pool = original_pool
    for guild_id in (GUILD_SOURCE, GUILD_TARGET_ADERENTE, GUILD_TARGET_NON_ADERENTE):
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
    await database.pool.execute(
        "DELETE FROM global_ban_log WHERE source_guild_id = $1", GUILD_SOURCE
    )
    await database.close()


@pytest.mark.asyncio
async def test_propaga_solo_verso_i_server_aderenti(contesto):
    await contesto.set_module_active_for_guild(GUILD_SOURCE, MODULE_GLOBAL_BAN, True)
    await contesto.set_module_active_for_guild(GUILD_TARGET_ADERENTE, MODULE_GLOBAL_BAN, True)
    # GUILD_TARGET_NON_ADERENTE resta senza il modulo attivo.

    sorgente = _FakeGuild(GUILD_SOURCE, "Server Sorgente")
    aderente = _FakeGuild(GUILD_TARGET_ADERENTE, "Server Aderente")
    non_aderente = _FakeGuild(GUILD_TARGET_NON_ADERENTE, "Server Non Aderente")
    bot = _FakeBot([sorgente, aderente, non_aderente])

    propagati = await propagate_ban(bot, sorgente, USER_ID, "Spam trap triggered")

    assert propagati == [GUILD_TARGET_ADERENTE]
    assert aderente.banned == [USER_ID]
    assert non_aderente.banned == []
    assert sorgente.banned == []  # non propaga mai su se stesso


@pytest.mark.asyncio
async def test_se_la_sorgente_non_ha_aderito_non_propaga_a_nessuno(contesto):
    await contesto.set_module_active_for_guild(GUILD_TARGET_ADERENTE, MODULE_GLOBAL_BAN, True)
    # GUILD_SOURCE non ha aderito.

    sorgente = _FakeGuild(GUILD_SOURCE, "Server Sorgente")
    aderente = _FakeGuild(GUILD_TARGET_ADERENTE, "Server Aderente")
    bot = _FakeBot([sorgente, aderente])

    propagati = await propagate_ban(bot, sorgente, USER_ID, "motivo")

    assert propagati == []
    assert aderente.banned == []


@pytest.mark.asyncio
async def test_un_errore_su_un_server_non_blocca_gli_altri(contesto):
    GUILD_TARGET_FORBIDDEN = 800000103
    await contesto.set_module_active_for_guild(GUILD_SOURCE, MODULE_GLOBAL_BAN, True)
    await contesto.set_module_active_for_guild(GUILD_TARGET_ADERENTE, MODULE_GLOBAL_BAN, True)
    await contesto.set_module_active_for_guild(GUILD_TARGET_FORBIDDEN, MODULE_GLOBAL_BAN, True)

    sorgente = _FakeGuild(GUILD_SOURCE, "Server Sorgente")
    aderente = _FakeGuild(GUILD_TARGET_ADERENTE, "Server Aderente")
    con_errore = _FakeGuild(GUILD_TARGET_FORBIDDEN, "Server Senza Permessi", raise_forbidden=True)
    bot = _FakeBot([sorgente, con_errore, aderente])

    try:
        propagati = await propagate_ban(bot, sorgente, USER_ID, "motivo")
    finally:
        await contesto.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", GUILD_TARGET_FORBIDDEN
        )

    assert GUILD_TARGET_ADERENTE in propagati
    assert GUILD_TARGET_FORBIDDEN not in propagati
    assert aderente.banned == [USER_ID]


@pytest.mark.asyncio
async def test_propagazione_viene_registrata_nel_log(contesto):
    await contesto.set_module_active_for_guild(GUILD_SOURCE, MODULE_GLOBAL_BAN, True)
    await contesto.set_module_active_for_guild(GUILD_TARGET_ADERENTE, MODULE_GLOBAL_BAN, True)

    sorgente = _FakeGuild(GUILD_SOURCE, "Server Sorgente")
    aderente = _FakeGuild(GUILD_TARGET_ADERENTE, "Server Aderente")
    bot = _FakeBot([sorgente, aderente])

    await propagate_ban(bot, sorgente, USER_ID, "Spam trap triggered")

    from core.repositories.global_ban_repo import global_ban_repo

    outgoing = await global_ban_repo.get_recent_outgoing(GUILD_SOURCE)
    assert len(outgoing) == 1
    assert outgoing[0].target_guild_id == GUILD_TARGET_ADERENTE
    assert outgoing[0].user_id == USER_ID
