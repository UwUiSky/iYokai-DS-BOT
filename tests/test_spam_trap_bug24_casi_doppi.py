"""
tests/test_spam_trap_bug24_casi_doppi.py
============================================
BUG-24: due casi `spam_trap_ban` attivi per lo stesso utente nello
STESSO server non devono bloccare l'appello in DM ("active bans on
multiple servers: Alpha, Alpha"), e `/unban` (come il bottone Unban
dell'appello) deve revocare tutti i casi spam-trap attivi dell'utente
in quel server.

Database vero (clean_db) e repository veri; di Discord solo i finti
fedeli di tests/support/discord_fakes.py.
"""

from unittest.mock import create_autospec

import discord
import pytest
from discord.ext import commands

from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.actions import ModerationActionsCog
from cogs.security.spam_trap import BAN_ACTION_TYPE, AppealActionsView, SpamTrapCog
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from core.repositories.spam_trap_repo import spam_trap_repo
from core.spam_trap_rate_tracker import limite_dm_appello
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_message,
    fake_text_channel,
)

ID_ALPHA = 100
ID_BETA = 200
ID_UTENTE = 42
ID_BOT = 999
ID_CANALE_LOG = 7002


@pytest.fixture(autouse=True)
def _ambiente_pulito(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    spam_trap_repo._config_cache.clear()
    limite_dm_appello.azzera()
    yield
    limite_dm_appello.azzera()
    spam_trap_repo._config_cache.clear()
    database_module.db._modules_cache.clear()


async def _ban_dalla_trappola(guild_id: int) -> int:
    """Lo stesso caso che la trappola registra quando banna qualcuno."""
    return await moderation_repo.create_case(
        guild_id=guild_id,
        user_id=ID_UTENTE,
        moderator_id=ID_BOT,
        action_type=BAN_ACTION_TYPE,
        reason="Triggered the spam trap channel",
    )


async def _casi_attivi(guild_id: int) -> list[int]:
    casi = await moderation_repo.get_active_cases_for_user_across_guilds(
        ID_UTENTE, BAN_ACTION_TYPE
    )
    return sorted(c.case_number for c in casi if c.guild_id == guild_id)


def _server_con_canale_log(guild_id: int, nome: str):
    server = fake_guild(guild_id, nome)
    canale_log = fake_text_channel(ID_CANALE_LOG, "spam-log")
    canale_log.create_thread.return_value = create_autospec(discord.Thread, instance=True)
    server.get_channel.return_value = canale_log
    return server, canale_log


def _cog_con_server(*server) -> SpamTrapCog:
    per_id = {s.id: s for s in server}
    bot = create_autospec(commands.Bot, instance=True)
    bot.get_guild.side_effect = per_id.get
    return SpamTrapCog(bot)


def _dm(contenuto: str):
    utente = create_autospec(discord.User, instance=True)
    utente.id = ID_UTENTE
    utente.mention = f"<@{ID_UTENTE}>"
    canale_dm = create_autospec(discord.DMChannel, instance=True)
    messaggio = fake_message(author=utente, channel=canale_dm, content=contenuto)
    messaggio.guild = None
    return messaggio


def _testi_inviati(messaggio) -> list[str]:
    return [chiamata.args[0] for chiamata in messaggio.channel.send.await_args_list]


class TestAppelloConCasiDoppi:
    @pytest.mark.asyncio
    async def test_due_casi_nello_stesso_server_aprono_un_solo_appello(self):
        await _ban_dalla_trappola(ID_ALPHA)
        caso_recente = await _ban_dalla_trappola(ID_ALPHA)
        await spam_trap_repo.set_config(ID_ALPHA, 7001, ID_CANALE_LOG)
        server, canale_log = _server_con_canale_log(ID_ALPHA, "Alpha")
        cog = _cog_con_server(server)
        messaggio = _dm("I was banned by mistake from Alpha")

        await cog._handle_possible_appeal(messaggio)

        testi = _testi_inviati(messaggio)
        assert not any("multiple servers" in testo for testo in testi), testi
        # L'appello parte sul caso più recente del server.
        canale_log.create_thread.assert_awaited_once()
        assert (
            canale_log.create_thread.await_args.kwargs["name"]
            == f"appeal-case-{caso_recente}"
        )
        assert any("submitted" in testo for testo in testi)

    @pytest.mark.asyncio
    async def test_la_domanda_quale_server_elenca_ogni_server_una_volta(self):
        await _ban_dalla_trappola(ID_ALPHA)
        await _ban_dalla_trappola(ID_ALPHA)
        await _ban_dalla_trappola(ID_BETA)
        alpha, _ = _server_con_canale_log(ID_ALPHA, "Alpha")
        beta, _ = _server_con_canale_log(ID_BETA, "Beta")
        cog = _cog_con_server(alpha, beta)
        messaggio = _dm("please unban me")

        await cog._handle_possible_appeal(messaggio)

        testi = _testi_inviati(messaggio)
        assert len(testi) == 1
        assert "multiple servers" in testi[0]
        assert testi[0].count("Alpha") == 1
        assert testi[0].count("Beta") == 1

    @pytest.mark.asyncio
    async def test_nominare_il_server_sblocca_l_appello_anche_con_casi_doppi(self):
        await _ban_dalla_trappola(ID_ALPHA)
        caso_recente = await _ban_dalla_trappola(ID_ALPHA)
        await _ban_dalla_trappola(ID_BETA)
        await spam_trap_repo.set_config(ID_ALPHA, 7001, ID_CANALE_LOG)
        alpha, canale_log = _server_con_canale_log(ID_ALPHA, "Alpha")
        beta, _ = _server_con_canale_log(ID_BETA, "Beta")
        cog = _cog_con_server(alpha, beta)
        messaggio = _dm("It's about alpha")

        await cog._handle_possible_appeal(messaggio)

        assert (
            canale_log.create_thread.await_args.kwargs["name"]
            == f"appeal-case-{caso_recente}"
        )


class TestUnbanRevocaICasiSpamTrap:
    @pytest.mark.asyncio
    async def test_unban_revoca_tutti_i_casi_spam_trap_del_server(self):
        await _ban_dalla_trappola(ID_ALPHA)
        await _ban_dalla_trappola(ID_ALPHA)
        caso_beta = await _ban_dalla_trappola(ID_BETA)
        await db.set_module_active_for_guild(ID_ALPHA, MODULE_ACTIONS, True)
        interazione = fake_interaction(guild=fake_guild(ID_ALPHA, "Alpha"))
        cog = ModerationActionsCog(create_autospec(commands.Bot, instance=True))

        await cog.unban.callback(
            cog, interazione, user_id=str(ID_UTENTE), reason="Appello accolto a voce"
        )

        interazione.guild.unban.assert_awaited_once()
        assert await _casi_attivi(ID_ALPHA) == []
        # I ban della trappola negli ALTRI server non si toccano.
        assert await _casi_attivi(ID_BETA) == [caso_beta]

    @pytest.mark.asyncio
    async def test_dopo_unban_un_dm_non_apre_piu_un_appello(self):
        await _ban_dalla_trappola(ID_ALPHA)
        await db.set_module_active_for_guild(ID_ALPHA, MODULE_ACTIONS, True)
        server, canale_log = _server_con_canale_log(ID_ALPHA, "Alpha")
        interazione = fake_interaction(guild=server)
        azioni = ModerationActionsCog(create_autospec(commands.Bot, instance=True))
        await azioni.unban.callback(
            azioni, interazione, user_id=str(ID_UTENTE), reason="Ban per errore"
        )
        messaggio = _dm("hello again")

        await _cog_con_server(server)._handle_possible_appeal(messaggio)

        assert _testi_inviati(messaggio) == []
        canale_log.create_thread.assert_not_awaited()


class TestBottoneUnbanDellAppello:
    @pytest.mark.asyncio
    async def test_revoca_anche_i_casi_spam_trap_piu_vecchi(self):
        await _ban_dalla_trappola(ID_ALPHA)
        caso_recente = await _ban_dalla_trappola(ID_ALPHA)
        server = fake_guild(ID_ALPHA, "Alpha")
        interazione = fake_interaction(guild=server)
        interazione.client = create_autospec(commands.Bot, instance=True)
        interazione.client.get_guild.return_value = server
        interazione.client.fetch_user.return_value = create_autospec(
            discord.User, instance=True
        )
        view = AppealActionsView(ID_ALPHA, caso_recente, ID_UTENTE)

        await view.unban.callback(interazione)

        server.unban.assert_awaited_once()
        assert await _casi_attivi(ID_ALPHA) == []
