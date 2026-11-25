"""
tests/test_global_ban_behavior.py
=====================================
Test di comportamento reale di propagate_ban() (SPEC.md §7.3) —
stesso schema di tests/test_anti_raid_behavior.py: un bot e dei
server discord.py finti contro un database Postgres reale, per
l'opt-in del modulo (che usa l'attivazione modulo generica già
esistente, `db.is_module_active_for_guild`).
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

import cogs.security.global_ban as global_ban_module
from cogs.security.global_ban import MODULE_GLOBAL_BAN, propagate_ban
from core.database import Database
from core.repositories.global_ban_repo import global_ban_repo
from core.repositories.rete_repo import rete_repo


class _FakeHTTPResponse:
    status = 403
    reason = "Forbidden"


class _FakeGuild:
    def __init__(self, guild_id: int, name: str, raise_forbidden: bool = False) -> None:
        self.id = guild_id
        self.name = name
        self.banned: list[int] = []
        self.raise_forbidden = raise_forbidden
        # Un server grande e vecchio: punteggio alto, il bot può bannare.
        self.member_count = 600
        self.created_at = discord.utils.utcnow() - timedelta(days=400)
        self.me = SimpleNamespace(
            id=1, joined_at=discord.utils.utcnow() - timedelta(days=90),
            guild_permissions=discord.Permissions(ban_members=True), top_role=0,
        )
        self.owner = SimpleNamespace(send=AsyncMock())
        self.owner_id = 1

    def get_member(self, user_id):
        return None

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
MOTIVO = "Ha scritto nel canale trappola e mandato link"


async def _aderisci(database, guild_id):
    """Il server aderisce alla rete in invio e ricezione, con ban automatico (di base è tutto spento)."""
    await database.set_module_active_for_guild(guild_id, MODULE_GLOBAL_BAN, True)
    await global_ban_repo.set_direction(guild_id, send=True, receive=True)
    await rete_repo.imposta(guild_id, ban_modo="automatico")


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
    for tabella, colonna in (
        ("global_ban_episodi", "source_guild_id"), ("rete_ban_proposte", "guild_origine"),
        ("rete_impostazioni", "guild_id"), ("global_ban_direction", "guild_id"),
    ):
        await database.pool.execute(
            f"DELETE FROM {tabella} WHERE {colonna} = ANY($1::bigint[])",  # nome da elenco fisso, valori come parametri
            [GUILD_SOURCE, GUILD_TARGET_ADERENTE, GUILD_TARGET_NON_ADERENTE, 800000103],
        )
    await database.pool.execute("DELETE FROM rete_ban_proposte WHERE guild_dest = ANY($1::bigint[])",
                                [GUILD_TARGET_ADERENTE, GUILD_TARGET_NON_ADERENTE, 800000103])

    monkeypatch.setattr(global_ban_module, "db", database)

    from core.database import db as real_db_singleton

    original_pool = real_db_singleton._pool
    real_db_singleton._pool = database.pool

    original_provider = global_ban_repo._pool_provider
    global_ban_repo._pool_provider = lambda: database.pool
    rete_originale = rete_repo._pool_provider
    rete_repo._pool_provider = lambda: database.pool

    yield database

    global_ban_repo._pool_provider = original_provider
    rete_repo._pool_provider = rete_originale
    real_db_singleton._pool = original_pool
    for guild_id in (GUILD_SOURCE, GUILD_TARGET_ADERENTE, GUILD_TARGET_NON_ADERENTE):
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
    await database.pool.execute(
        "DELETE FROM global_ban_log WHERE source_guild_id = $1", GUILD_SOURCE
    )
    for tabella, colonna in (
        ("global_ban_episodi", "source_guild_id"), ("rete_ban_proposte", "guild_origine"),
        ("rete_impostazioni", "guild_id"), ("global_ban_direction", "guild_id"),
    ):
        await database.pool.execute(
            f"DELETE FROM {tabella} WHERE {colonna} = ANY($1::bigint[])",  # nome da elenco fisso, valori come parametri
            [GUILD_SOURCE, GUILD_TARGET_ADERENTE, GUILD_TARGET_NON_ADERENTE, 800000103],
        )
    await database.pool.execute("DELETE FROM rete_ban_proposte WHERE guild_dest = ANY($1::bigint[])",
                                [GUILD_TARGET_ADERENTE, GUILD_TARGET_NON_ADERENTE, 800000103])
    await database.close()


@pytest.mark.asyncio
async def test_propaga_solo_verso_i_server_aderenti(contesto):
    await _aderisci(contesto, GUILD_SOURCE)
    await _aderisci(contesto, GUILD_TARGET_ADERENTE)
    # GUILD_TARGET_NON_ADERENTE resta senza il modulo attivo.

    sorgente = _FakeGuild(GUILD_SOURCE, "Server Sorgente")
    aderente = _FakeGuild(GUILD_TARGET_ADERENTE, "Server Aderente")
    non_aderente = _FakeGuild(GUILD_TARGET_NON_ADERENTE, "Server Non Aderente")
    bot = _FakeBot([sorgente, aderente, non_aderente])

    propagati = await propagate_ban(bot, sorgente, USER_ID, MOTIVO, con_prova=True)

    assert propagati == [GUILD_TARGET_ADERENTE]
    assert aderente.banned == [USER_ID]
    assert non_aderente.banned == []
    assert sorgente.banned == []  # non propaga mai su se stesso


@pytest.mark.asyncio
async def test_se_la_sorgente_non_ha_aderito_non_propaga_a_nessuno(contesto):
    await _aderisci(contesto, GUILD_TARGET_ADERENTE)
    # GUILD_SOURCE non ha aderito.

    sorgente = _FakeGuild(GUILD_SOURCE, "Server Sorgente")
    aderente = _FakeGuild(GUILD_TARGET_ADERENTE, "Server Aderente")
    bot = _FakeBot([sorgente, aderente])

    propagati = await propagate_ban(bot, sorgente, USER_ID, MOTIVO, con_prova=True)

    assert propagati == []
    assert aderente.banned == []


@pytest.mark.asyncio
async def test_un_errore_su_un_server_non_blocca_gli_altri(contesto):
    GUILD_TARGET_FORBIDDEN = 800000103
    await _aderisci(contesto, GUILD_SOURCE)
    await _aderisci(contesto, GUILD_TARGET_ADERENTE)
    await _aderisci(contesto, GUILD_TARGET_FORBIDDEN)

    sorgente = _FakeGuild(GUILD_SOURCE, "Server Sorgente")
    aderente = _FakeGuild(GUILD_TARGET_ADERENTE, "Server Aderente")
    con_errore = _FakeGuild(GUILD_TARGET_FORBIDDEN, "Server Senza Permessi", raise_forbidden=True)
    bot = _FakeBot([sorgente, con_errore, aderente])

    try:
        propagati = await propagate_ban(bot, sorgente, USER_ID, MOTIVO, con_prova=True)
    finally:
        await contesto.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = $1", GUILD_TARGET_FORBIDDEN
        )

    assert GUILD_TARGET_ADERENTE in propagati
    assert GUILD_TARGET_FORBIDDEN not in propagati
    assert aderente.banned == [USER_ID]


@pytest.mark.asyncio
async def test_propagazione_viene_registrata_nel_log(contesto):
    await _aderisci(contesto, GUILD_SOURCE)
    await _aderisci(contesto, GUILD_TARGET_ADERENTE)

    sorgente = _FakeGuild(GUILD_SOURCE, "Server Sorgente")
    aderente = _FakeGuild(GUILD_TARGET_ADERENTE, "Server Aderente")
    bot = _FakeBot([sorgente, aderente])

    await propagate_ban(bot, sorgente, USER_ID, MOTIVO, con_prova=True)

    outgoing = await global_ban_repo.get_recent_outgoing(GUILD_SOURCE)
    assert len(outgoing) == 1
    assert outgoing[0].target_guild_id == GUILD_TARGET_ADERENTE
    assert outgoing[0].user_id == USER_ID
