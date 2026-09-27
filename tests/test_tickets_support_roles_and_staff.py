"""
tests/test_tickets_support_roles_and_staff.py
==================================================
Test di _support_role_ids/_is_ticket_staff (cogs/tickets/tickets.py,
SPEC.md §13.9/§13.13) contro PostgreSQL reale — stesso pattern di
tests/test_moderation_shared_new_helpers.py: il pool di test viene
collegato con monkeypatch sull'attributo privato _pool del singleton
REALE core.database.db.
"""

from unittest.mock import Mock

import discord
import pytest

from cogs.tickets.tickets import (
    SETTING_SUPPORT_ROLE,
    SETTING_SUPPORT_ROLES,
    _is_ticket_staff,
    _support_role_ids,
)


def _collega_pool_di_test(monkeypatch, clean_db) -> None:
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()


class _FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id


class _FakePermissions:
    def __init__(self, manage_guild: bool = False) -> None:
        self.manage_guild = manage_guild


def _fake_member(member_id: int, roles: list[_FakeRole], manage_guild: bool = False):
    """
    Mock(spec=discord.Member) invece di una sottoclasse: discord.Member
    calcola id/roles tramite property che delegano a stato interno
    (_user/_roles) non disponibile in un test — un Mock con spec
    passa comunque isinstance(x, discord.Member), che è tutto ciò
    che serve a _is_ticket_staff.
    """
    member = Mock(spec=discord.Member)
    member.id = member_id
    member.roles = roles
    member.guild_permissions = _FakePermissions(manage_guild)
    return member


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeInteraction:
    def __init__(self, guild: _FakeGuild, user) -> None:
        self.guild = guild
        self.user = user


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    _collega_pool_di_test(monkeypatch, clean_db)
    return clean_db


class TestSupportRoleIds:
    @pytest.mark.asyncio
    async def test_nessun_ruolo_configurato(self):
        assert await _support_role_ids(100) == []

    @pytest.mark.asyncio
    async def test_solo_ruolo_legacy(self):
        from core.database import db

        await db.set_guild_setting(100, SETTING_SUPPORT_ROLE, 42)
        assert await _support_role_ids(100) == [42]

    @pytest.mark.asyncio
    async def test_legacy_e_lista_combinati_senza_duplicati(self):
        from core.database import db

        await db.set_guild_setting(100, SETTING_SUPPORT_ROLE, 42)
        await db.set_guild_setting(100, SETTING_SUPPORT_ROLES, [42, 99])
        assert await _support_role_ids(100) == [42, 99]


class TestIsTicketStaff:
    @pytest.mark.asyncio
    async def test_manage_guild_e_staff(self):
        guild = _FakeGuild(100)
        member = _fake_member(1, roles=[], manage_guild=True)
        interaction = _FakeInteraction(guild, member)
        assert await _is_ticket_staff(interaction) is True

    @pytest.mark.asyncio
    async def test_ruolo_di_supporto_e_staff(self):
        from core.database import db

        await db.set_guild_setting(100, SETTING_SUPPORT_ROLES, [42])
        guild = _FakeGuild(100)
        member = _fake_member(1, roles=[_FakeRole(42)], manage_guild=False)
        interaction = _FakeInteraction(guild, member)
        assert await _is_ticket_staff(interaction) is True

    @pytest.mark.asyncio
    async def test_utente_qualunque_non_e_staff(self):
        guild = _FakeGuild(100)
        member = _fake_member(1, roles=[_FakeRole(1)], manage_guild=False)
        interaction = _FakeInteraction(guild, member)
        assert await _is_ticket_staff(interaction) is False
