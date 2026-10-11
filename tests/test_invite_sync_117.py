"""
tests/test_invite_sync_117.py
=============================
Difetti di invite_sync trovati leggendo:
- `invite.guild` non e' sempre un `Guild` (puo' essere un `Object` o un
  `PartialInviteGuild`): rileggere gli inviti lanciava AttributeError;
- un errore leggendo gli inviti di un server rompeva il listener
  (on_guild_join, on_invite_create/delete) invece di restare nei log.
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.security.invite_sync as modulo
from core.database import Database
from tests.support.discord_fakes import fake_guild


@pytest.fixture
def cog(monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", db_finto)
    tracker = MagicMock()
    tracker.refresh_guild = AsyncMock()
    monkeypatch.setattr(modulo, "invite_tracker", tracker)
    bot = create_autospec(commands.Bot, instance=True)
    server = fake_guild(100)
    bot.get_guild.side_effect = lambda gid: server if gid == 100 else None
    cog = modulo.InviteSyncCog(bot)
    cog.server_vero = server
    cog.tracker = tracker
    return cog


async def test_invito_con_guild_parziale_si_risolve_dal_bot(cog):
    invito = MagicMock()
    invito.guild = discord.Object(id=100)  # non un Guild
    await cog.on_invite_create(invito)
    cog.tracker.refresh_guild.assert_awaited_once_with(cog.server_vero)


async def test_invito_di_un_server_sconosciuto_non_fa_niente(cog):
    invito = MagicMock()
    invito.guild = discord.Object(id=555)
    await cog.on_invite_delete(invito)
    cog.tracker.refresh_guild.assert_not_awaited()


async def test_un_errore_non_esce_dal_listener(cog, caplog):
    cog.tracker.refresh_guild.side_effect = RuntimeError("boom")
    invito = MagicMock()
    invito.guild = cog.server_vero
    await cog.on_invite_create(invito)  # non solleva
    await cog.on_guild_join(cog.server_vero)  # non solleva
    assert "boom" in caplog.text or "inviti" in caplog.text.lower()
