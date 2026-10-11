"""
tests/test_scheduled_messages_limiti.py
==========================================
M 10.5 (LIM-12, LIM-13) e M 10.6 (D12): messaggi programmati e
promemoria non si perdono in silenzio; i ping seguono il permesso.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.reminders as reminders_module
import cogs.utility.scheduled_messages as sched_module
from cogs.utility.reminders import RemindersCog
from cogs.utility.scheduled_messages import ScheduledMessagesCog
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel


def _errore_http(status=403):
    return discord.HTTPException(MagicMock(status=status, reason="x"), "errore")


def _bot_con_canale(canale, autore=None):
    guild = fake_guild(guild_id=100)
    guild.get_channel = MagicMock(return_value=canale)
    bot = MagicMock()
    bot.get_guild.return_value = guild
    bot.get_user.return_value = autore
    return bot


def _canale(invio=None):
    canale = fake_text_channel(channel_id=500)
    canale.__class__ = discord.TextChannel
    canale.send = AsyncMock(side_effect=invio)
    return canale


@pytest.mark.asyncio
async def test_invio_fallito_l_autore_lo_sa():
    autore = MagicMock()
    autore.send = AsyncMock()
    canale = _canale(invio=_errore_http())
    cog = ScheduledMessagesCog(_bot_con_canale(canale, autore))

    await cog.handle_scheduled_message_fire(
        100, 7, {"channel_id": 500, "message": "Evento stasera!"}
    )

    autore.send.assert_awaited_once()
    assert "non è stato pubblicato" in autore.send.await_args.args[0]


@pytest.mark.asyncio
async def test_canale_sparito_l_autore_lo_sa():
    autore = MagicMock()
    autore.send = AsyncMock()
    bot = _bot_con_canale(None, autore)
    cog = ScheduledMessagesCog(bot)

    await cog.handle_scheduled_message_fire(100, 7, {"channel_id": 999, "message": "x"})

    autore.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_autore_con_dm_chiusi_non_solleva():
    autore = MagicMock()
    autore.send = AsyncMock(side_effect=_errore_http())
    cog = ScheduledMessagesCog(_bot_con_canale(_canale(invio=_errore_http()), autore))
    await cog.handle_scheduled_message_fire(100, 7, {"channel_id": 500, "message": "x"})


@pytest.mark.asyncio
async def test_ping_di_ruolo_attivo_ma_everyone_muto():
    canale = _canale()
    cog = ScheduledMessagesCog(_bot_con_canale(canale))
    await cog.handle_scheduled_message_fire(
        100, 7, {"channel_id": 500, "message": "<@&5> @everyone", "ping_ruoli": True}
    )
    menzioni = canale.send.await_args.kwargs["allowed_mentions"]
    assert menzioni.roles is True and menzioni.everyone is False

    canale2 = _canale()
    cog = ScheduledMessagesCog(_bot_con_canale(canale2))
    await cog.handle_scheduled_message_fire(100, 7, {"channel_id": 500, "message": "<@&5>"})
    assert canale2.send.await_args.kwargs["allowed_mentions"].roles is False


@pytest.mark.asyncio
async def test_programma_salva_il_permesso_dell_autore(monkeypatch):
    monkeypatch.setattr(sched_module.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    schedula = AsyncMock(return_value=1)
    monkeypatch.setattr(sched_module.scheduler, "schedule", schedula)
    cog = ScheduledMessagesCog(MagicMock())
    utente = fake_member(guild_permissions=discord.Permissions(mention_everyone=True))
    canale = fake_text_channel(channel_id=500)

    await cog.set_scheduled_message.callback(
        cog, fake_interaction(guild=fake_guild(guild_id=100), user=utente), canale, "1h", "Ciao"
    )

    assert schedula.await_args.kwargs["payload"]["ping_ruoli"] is True


@pytest.mark.asyncio
async def test_lista_programmati_resta_sotto_4096(monkeypatch):
    azioni = [
        {"id": i, "execute_at": datetime.now(timezone.utc) + timedelta(hours=i),
         "payload": {"channel_id": 500, "message": "m" * 500}}
        for i in range(60)
    ]
    monkeypatch.setattr(
        sched_module.scheduler, "list_pending_for_guild", AsyncMock(return_value=azioni)
    )
    interazione = fake_interaction(guild=fake_guild(guild_id=100))
    cog = ScheduledMessagesCog(MagicMock())

    await cog.list_scheduled_messages.callback(cog, interazione)

    embed = interazione.response.send_message.await_args.kwargs["embed"]
    assert len(embed.description) <= 4096
    assert "altre" in embed.description


@pytest.mark.asyncio
async def test_lista_promemoria_resta_sotto_4096(monkeypatch):
    azioni = [
        {"id": i, "execute_at": datetime.now(timezone.utc) + timedelta(hours=i),
         "payload": {"message": "m" * 1800}}
        for i in range(25)
    ]
    monkeypatch.setattr(
        reminders_module.scheduler, "list_pending_for_user", AsyncMock(return_value=azioni)
    )
    interazione = fake_interaction()
    cog = RemindersCog(MagicMock())

    await cog.list_reminders.callback(cog, interazione)

    embed = interazione.response.send_message.await_args.kwargs["embed"]
    assert len(embed.description) <= 4096


@pytest.mark.asyncio
async def test_promemoria_nel_canale_non_puo_pingare_everyone_ne_ruoli():
    canale = _canale()
    bot = _bot_con_canale(canale)
    bot.get_user.return_value = None
    bot.fetch_user = AsyncMock(side_effect=_errore_http(404))
    cog = RemindersCog(bot)

    await cog.handle_reminder_fire(100, 7, {"message": "@everyone <@&5>", "channel_id": 500})

    menzioni = canale.send.await_args.kwargs["allowed_mentions"]
    assert menzioni.everyone is False and menzioni.roles is False
    assert [u.id for u in menzioni.users] == [7]


@pytest.mark.asyncio
async def test_testo_dei_comandi_ha_il_limite_1800():
    from discord.ext import commands

    from cogs.utility.reminders import setup as reminders_setup
    from cogs.utility.scheduled_messages import setup as sched_setup
    from tests.support.percorsi import comando_nel_gruppo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await sched_setup(bot)
    await reminders_setup(bot)

    for gruppo, percorso in (("admin", "messaggi programma"), ("utility", "reminder set")):
        opzioni = {o["name"]: o for o in comando_nel_gruppo(gruppo, percorso).to_dict(bot.tree)["options"]}
        assert opzioni["message"]["max_length"] == 1800, percorso
        assert opzioni["message"]["min_length"] == 1, percorso
