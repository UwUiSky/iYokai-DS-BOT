"""
tests/test_moderation_lock_tempo.py
===================================
Lock a tempo (MOD-090) e sanzioni a tempo attive (MOD-013). Lo sblocco è
un'azione dello scheduler (database vero) che rimette il permesso di prima.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_CASE_SYSTEM, MODULE_CHANNEL_CONTROL
from cogs.moderation.case_system import ModerationCaseSystemCog, righe_sanzioni_attive
from cogs.moderation.channel_control import (
    SCHEDULED_CHANNEL_UNLOCK,
    ModerationChannelControlCog,
)
from core.database import db
from core.scheduler import scheduler
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

SERVER = 100
CANALE = 5005


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(SERVER, MODULE_CHANNEL_CONTROL, True)
    await db.set_module_active_for_guild(SERVER, MODULE_CASE_SYSTEM, True)
    yield
    database_module.db._modules_cache.clear()


def _scena(prima=None):
    server = fake_guild(SERVER, owner_id=1)
    server.members = []
    canale = fake_text_channel(CANALE, "generale")
    canale.guild = server
    permessi = discord.PermissionOverwrite(send_messages=prima)
    canale.overwrites_for = MagicMock(side_effect=lambda _r: discord.PermissionOverwrite(**{
        k: v for k, v in permessi
    }))

    async def _set(ruolo, overwrite, reason=None):
        permessi.update(send_messages=overwrite.send_messages)

    canale.set_permissions = AsyncMock(side_effect=_set)
    server.get_channel.return_value = canale
    interazione = fake_interaction(guild=server, user=fake_member(7))
    return server, canale, permessi, interazione


def _cog(server):
    bot = MagicMock()
    bot.get_guild.return_value = server
    return ModerationChannelControlCog(bot)


async def _attese():
    return await scheduler.list_pending_for_guild(SERVER, SCHEDULED_CHANNEL_UNLOCK)


async def test_lock_a_tempo_pianifica_lo_sblocco_e_rimette_il_permesso_di_prima():
    server, canale, permessi, interazione = _scena(prima=True)
    cog = _cog(server)
    await cog.lock.callback(cog, interazione, canale, "raid", "30m")

    assert permessi.send_messages is False
    [attesa] = await _attese()
    assert attesa["user_id"] == CANALE and attesa["payload"] == {"prima": True}
    delta = attesa["execute_at"] - discord.utils.utcnow()
    assert timedelta(minutes=29) < delta <= timedelta(minutes=30)

    await cog.handle_unlock(SERVER, CANALE, attesa["payload"])
    assert permessi.send_messages is True  # come prima, non «ereditato»


async def test_sblocco_a_mano_annulla_l_attesa_e_lo_scheduler_non_tocca_un_canale_gia_aperto():
    server, canale, permessi, interazione = _scena(prima=None)
    cog = _cog(server)
    await cog.lock.callback(cog, interazione, canale, None, "1h")
    await cog.unlock.callback(cog, interazione, canale)
    assert permessi.send_messages is None
    assert await _attese() == []

    # Un sblocco arrivato tardi su un canale già cambiato a mano: niente.
    permessi.update(send_messages=True)
    await cog.handle_unlock(SERVER, CANALE, {"prima": None})
    assert permessi.send_messages is True


async def test_secondo_lock_tiene_il_permesso_di_prima_del_primo():
    server, canale, permessi, interazione = _scena(prima=True)
    cog = _cog(server)
    await cog.lock.callback(cog, interazione, canale, None, "1h")
    await cog.lock.callback(cog, interazione, canale, None, "2h")
    [attesa] = await _attese()
    assert attesa["payload"] == {"prima": True}


async def test_durata_troppo_lunga_rifiutata():
    server, canale, permessi, interazione = _scena()
    cog = _cog(server)
    await cog.lock.callback(cog, interazione, canale, None, "31d")
    canale.set_permissions.assert_not_awaited()
    assert "30 giorni" in interazione.response.send_message.call_args.args[0]


async def test_sanzioni_attive():
    server, canale, permessi, interazione = _scena()
    await _cog(server).lock.callback(_cog(server), interazione, canale, None, "1h")
    membro = fake_member(42)
    membro.timed_out_until = discord.utils.utcnow() + timedelta(minutes=10)
    finito = fake_member(43)
    finito.timed_out_until = discord.utils.utcnow() - timedelta(minutes=1)
    server.members = [membro, finito]
    await scheduler.schedule(SERVER, 44, "moderation_tempban_expire",
                             discord.utils.utcnow() + timedelta(days=1), {"case_number": 9})

    righe = await righe_sanzioni_attive(server)
    testo = "\n".join(righe)
    assert "Tempban** <@44>" in testo and "caso #9" in testo
    assert "<@42>" in testo and "<@43>" not in testo
    assert f"<#{CANALE}>" in testo

    cog = ModerationCaseSystemCog(MagicMock())
    interazione = fake_interaction(guild=server)
    await cog.active.callback(cog, interazione)
    assert "Tempban" in interazione.followup.send.call_args.kwargs["embed"].description
