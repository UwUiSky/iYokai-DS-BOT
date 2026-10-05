"""
tests/test_giveaway_thread_e_forum.py
=====================================
M 9.15: un giveaway lanciato dentro un thread, un post di un forum o la
chat di un canale vocale annuncia i vincitori lì, anche se il thread
nel frattempo è stato archiviato (non è più in memoria). Database vero.
Funzioni coperte: SPEC §15.5
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import create_autospec

import discord
import pytest
from discord.ext import commands

from cogs.leveling.leveling import LevelingCog
from core.giveaway_worker import GiveawayWorker
from core.repositories.giveaway_repo import giveaway_repo
from tests.support.moduli import attiva_livelli
from tests.support.discord_fakes import (
    fake_forum_channel,
    fake_guild,
    fake_interaction,
    fake_member,
    fake_voice_channel,
)

GUILD_ID = 100
ID_THREAD = 700
VINCITORE = 7


class _RispostaHTTPFinta:
    status = 404
    reason = "Not Found"


@pytest.fixture
async def cog(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, GUILD_ID)
    c = LevelingCog(bot=None)
    c.cog_unload()
    return c


def _thread(thread_id: int = ID_THREAD):
    """Un thread vero per discord.py: anche il post di un forum è un Thread."""
    thread = create_autospec(discord.Thread, instance=True)
    thread.id = thread_id
    return thread


async def _giveaway_con_un_partecipante(cog, canale) -> None:
    """Il giveaway nasce dal comando vero, lanciato dentro `canale`; poi un utente partecipa."""
    lancio = fake_interaction(guild=fake_guild(GUILD_ID), channel=canale)
    lancio.original_response.return_value.id = 9001
    await cog.giveaway.callback(
        cog, lancio, prize="Nitro", duration_minutes=1, winners=1, min_level=0, required_role=None
    )
    view = lancio.response.send_message.await_args.kwargs["view"]
    await view._entra.callback(fake_interaction(user=fake_member(VINCITORE)))
    view.stop()


def _bot_con(server):
    bot = create_autospec(commands.Bot, instance=True)
    bot.get_guild.return_value = server
    return bot


async def _fine_del_giveaway(server) -> None:
    await GiveawayWorker().tick(_bot_con(server), now=datetime.now(timezone.utc) + timedelta(minutes=5))


@pytest.mark.asyncio
async def test_vincitore_avvisato_in_un_thread(cog):
    thread = _thread()
    await _giveaway_con_un_partecipante(cog, thread)
    server = fake_guild(GUILD_ID)
    server.get_channel_or_thread.side_effect = lambda cid: thread if cid == ID_THREAD else None

    await _fine_del_giveaway(server)

    testo = thread.send.await_args.args[0]
    assert f"<@{VINCITORE}>" in testo and "Nitro" in testo


@pytest.mark.asyncio
async def test_vincitore_avvisato_in_un_thread_archiviato(cog):
    """Un thread archiviato (o il post di un forum) non è in memoria: si chiede a Discord."""
    thread = _thread()
    await _giveaway_con_un_partecipante(cog, thread)
    server = fake_guild(GUILD_ID)
    server.get_channel_or_thread.return_value = None
    server.fetch_channel.return_value = thread

    await _fine_del_giveaway(server)

    server.fetch_channel.assert_awaited_once_with(ID_THREAD)
    assert f"<@{VINCITORE}>" in thread.send.await_args.args[0]


@pytest.mark.asyncio
async def test_vincitore_avvisato_nella_chat_di_un_canale_vocale(cog):
    vocale = fake_voice_channel(ID_THREAD)
    await _giveaway_con_un_partecipante(cog, vocale)
    server = fake_guild(GUILD_ID)
    server.get_channel_or_thread.return_value = vocale

    await _fine_del_giveaway(server)

    assert f"<@{VINCITORE}>" in vocale.send.await_args.args[0]


@pytest.mark.asyncio
async def test_canale_cancellato_il_giveaway_si_chiude_senza_errori(cog):
    thread = _thread()
    await _giveaway_con_un_partecipante(cog, thread)
    server = fake_guild(GUILD_ID)
    server.get_channel_or_thread.return_value = None
    server.fetch_channel.side_effect = discord.NotFound(_RispostaHTTPFinta(), "sparito")

    await _fine_del_giveaway(server)

    assert await giveaway_repo.get_due_giveaways(datetime.now(timezone.utc) + timedelta(days=1)) == []


@pytest.mark.asyncio
async def test_un_canale_dove_non_si_scrive_non_fa_esplodere_il_giro(cog):
    """Un forum (non il suo post) non accetta messaggi: nessun invio, nessun errore."""
    thread = _thread()
    await _giveaway_con_un_partecipante(cog, thread)
    server = fake_guild(GUILD_ID)
    server.get_channel_or_thread.return_value = fake_forum_channel(ID_THREAD)

    await _fine_del_giveaway(server)

    assert await giveaway_repo.get_due_giveaways(datetime.now(timezone.utc) + timedelta(days=1)) == []
