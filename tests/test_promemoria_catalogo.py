"""
tests/test_promemoria_catalogo.py
=================================
Catalogo #128: promemoria che si ripete (UTL-098), nel canale (UTL-099),
annullare tutti i propri (UTL-102), lo staff vede e annulla quelli del
server (UTL-103). Scheduler finto: si prova solo il cog.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.reminders as modulo
from cogs.utility.reminders import REMINDER_ACTION_TYPE, RemindersCog
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel
from tests.support.percorsi import comando_nel_gruppo


@pytest.fixture
def sched(monkeypatch):
    finto = MagicMock(
        schedule=AsyncMock(return_value=42),
        cancel=AsyncMock(),
        list_pending_for_user=AsyncMock(return_value=[]),
        list_pending_for_guild=AsyncMock(return_value=[]),
        get_pending_action=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(modulo, "scheduler", finto)
    monkeypatch.setattr(modulo.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    return finto


@pytest.mark.asyncio
async def test_promemoria_ripetuto_e_nel_canale(sched):
    cog = RemindersCog(MagicMock())
    it = fake_interaction()
    await cog.set_reminder.callback(cog, it, "1h", "bevi", "1d", True)
    payload = sched.schedule.await_args.kwargs["payload"]
    assert payload["ripeti"] == 86400 and payload["nel_canale"] is True
    assert "ogni" in it.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_ripetizione_troppo_fitta_rifiutata(sched):
    cog = RemindersCog(MagicMock())
    it = fake_interaction()
    await cog.set_reminder.callback(cog, it, "1h", "bevi", "5m", False)
    sched.schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_allo_scatto_si_riprogramma_e_scrive_nel_canale(sched):
    canale = fake_text_channel(500)
    canale.send = AsyncMock()
    server = fake_guild(guild_id=100)
    server.get_channel = MagicMock(return_value=canale)
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=server)
    cog = RemindersCog(bot)
    payload = {"message": "bevi", "channel_id": 500, "ripeti": 3600, "nel_canale": True}
    await cog.handle_reminder_fire(100, 7, payload)
    assert sched.schedule.await_args.args[2] == REMINDER_ACTION_TYPE
    assert sched.schedule.await_args.args[4] == payload
    canale.send.assert_awaited_once()
    bot.get_user.assert_not_called()  # niente DM


@pytest.mark.asyncio
async def test_annulla_tutti_i_propri(sched):
    sched.list_pending_for_user.return_value = [{"id": 1}, {"id": 2}]
    cog = RemindersCog(MagicMock())
    it = fake_interaction()
    await cog.cancel_reminder.callback(cog, it, None, True)
    assert [c.args[0] for c in sched.cancel.await_args_list] == [1, 2]


@pytest.mark.asyncio
async def test_lo_staff_annulla_un_promemoria_del_server(sched, monkeypatch):
    server = fake_guild(guild_id=100)
    sched.get_pending_action.return_value = {
        "action_type": REMINDER_ACTION_TYPE, "executed": False, "user_id": 9, "guild_id": 100,
    }
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=True))
    cog = RemindersCog(MagicMock())
    it = fake_interaction(guild=server, user=fake_member(7))
    await cog.cancel_reminder.callback(cog, it, 5, False)
    sched.cancel.assert_awaited_once_with(5)
    # un membro qualunque no
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=False))
    sched.cancel.reset_mock()
    it2 = fake_interaction(guild=server, user=fake_member(8))
    await cog.cancel_reminder.callback(cog, it2, 5, False)
    sched.cancel.assert_not_awaited()


@pytest.mark.asyncio
async def test_elenco_del_server_solo_per_admin(sched, monkeypatch):
    from datetime import datetime, timezone

    sched.list_pending_for_guild.return_value = [
        {"id": 3, "user_id": 9, "execute_at": datetime.now(timezone.utc), "payload": {"message": "x"}}
    ]
    cog = RemindersCog(MagicMock())
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=False))
    it = fake_interaction()
    await cog.server_reminders.callback(cog, it)
    sched.list_pending_for_guild.assert_not_awaited()
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=True))
    it = fake_interaction()
    await cog.server_reminders.callback(cog, it)
    assert "`#3` <@9>" in it.response.send_message.await_args.kwargs["embed"].description


@pytest.mark.asyncio
async def test_comando_server_nel_sottogruppo():
    from discord.ext import commands as ext

    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    assert comando_nel_gruppo("utility", "reminder server") is not None
