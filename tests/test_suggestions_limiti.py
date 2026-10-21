"""
tests/test_suggestions_limiti.py
===================================
M 10.9 (LIM-25, REVIEW §5): `/suggest` risponde subito e ha un limite di
testo; due membri dello staff che decidono insieme producono UNA decisione.
Stesso per le richieste di comandi.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.custom_command_requests as ccr_module
import cogs.utility.suggestions as sg
from cogs.utility.custom_command_requests import CustomCommandRequestsCog
from cogs.utility.suggestions import SuggestionsCog
from core.repositories.custom_command_request_repo import CustomCommandRequestRepository
from core.repositories.suggestion_repo import SuggestionRepository
from core.suggestion_logic import APPROVED, REJECTED
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_text_channel
from tests.support.percorsi import comando_nel_gruppo


def _staff(user_id):
    return fake_member(user_id=user_id, guild_permissions=discord.Permissions(manage_guild=True))


@pytest.fixture
def repo(clean_db, monkeypatch):
    r = SuggestionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(sg, "suggestion_repo", r)
    monkeypatch.setattr(sg.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    monkeypatch.setattr(sg.db, "get_guild_setting", AsyncMock(return_value=None))
    return r


@pytest.mark.asyncio
async def test_set_status_decide_una_volta_sola(repo):
    sid = await repo.create_suggestion(1, 2, 3, "idea")
    ora = datetime.now(timezone.utc)
    assert await repo.set_status(sid, APPROVED, decided_by=10, decided_at=ora) is True
    assert await repo.set_status(sid, REJECTED, decided_by=11, decided_at=ora) is False
    s = await repo.get_suggestion(sid)
    assert s.status == APPROVED and s.decided_by == 10


@pytest.mark.asyncio
async def test_due_clic_insieme_una_sola_decisione(repo):
    sid = await repo.create_suggestion(1, 2, 3, "idea")
    await apri_connessioni(repo._pool)
    cog = SuggestionsCog(bot=MagicMock())
    i1 = fake_interaction(user=_staff(10))
    i2 = fake_interaction(user=_staff(11))

    await asyncio.gather(
        cog._handle_decision(i1, sid, APPROVED),
        cog._handle_decision(i2, sid, REJECTED),
    )

    modificati = [i for i in (i1, i2) if i.response.edit_message.await_count == 1]
    respinti = [i for i in (i1, i2) if i.response.send_message.await_count == 1]
    assert len(modificati) == 1 and len(respinti) == 1
    assert "già" in respinti[0].response.send_message.await_args.args[0]
    s = await repo.get_suggestion(sid)
    assert s.decided_by == modificati[0].user.id


@pytest.mark.asyncio
async def test_suggest_risponde_subito_e_pubblica_nel_followup(repo, monkeypatch):
    canale = fake_text_channel(channel_id=50)
    canale.__class__ = discord.TextChannel
    canale.send = AsyncMock(return_value=fake_message(message_id=900))
    monkeypatch.setattr(sg.db, "get_guild_setting", AsyncMock(return_value=50))
    guild = fake_guild(guild_id=1)
    guild.get_channel.return_value = canale
    interazione = fake_interaction(guild=guild, user=fake_member(user_id=3))
    bot = MagicMock()
    cog = SuggestionsCog(bot=bot)

    await cog.suggest.callback(cog, interazione, "Una idea")

    interazione.response.defer.assert_awaited_once()
    interazione.response.send_message.assert_not_awaited()
    interazione.followup.send.assert_awaited_once()
    assert (await repo.list_pending())[0].message_id == 900


@pytest.mark.asyncio
async def test_suggest_con_invio_fallito_non_lascia_righe_orfane(repo, monkeypatch):
    canale = fake_text_channel(channel_id=50)
    canale.__class__ = discord.TextChannel
    canale.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=400, reason="x"), "boom"))
    monkeypatch.setattr(sg.db, "get_guild_setting", AsyncMock(return_value=50))
    guild = fake_guild(guild_id=1)
    guild.get_channel.return_value = canale
    interazione = fake_interaction(guild=guild, user=fake_member(user_id=3))
    cog = SuggestionsCog(bot=MagicMock())

    await cog.suggest.callback(cog, interazione, "Una idea")

    assert await repo.list_pending(1) == []
    assert "non" in interazione.followup.send.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_testo_del_suggerimento_ha_il_limite_2000(clean_db):
    from core.database import db
    import cogs.utility.suggestions as modulo

    await db.connect()
    try:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        await modulo.setup(bot)
    finally:
        await db.close()
    opzioni = {o["name"]: o for o in comando_nel_gruppo("utility", "suggest").to_dict(bot.tree)["options"]}
    assert opzioni["text"]["max_length"] == 2000
    assert opzioni["text"]["min_length"] == 1


# ------------------------------------------------- richieste di comandi
@pytest.fixture
def repo_ccr(clean_db, monkeypatch):
    r = CustomCommandRequestRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(ccr_module, "custom_command_request_repo", r)
    return r


async def _nuova_richiesta(r):
    return await r.create_request(1, "S", 3, "u", "/ciao", "descrizione", "/ciao x")


@pytest.mark.asyncio
async def test_richiesta_decisa_una_volta_sola(repo_ccr):
    rid = await _nuova_richiesta(repo_ccr)
    ora = datetime.now(timezone.utc)
    assert await repo_ccr.set_status(rid, APPROVED, decided_by=10, decided_at=ora) is True
    assert await repo_ccr.set_status(rid, REJECTED, decided_by=11, decided_at=ora) is False


@pytest.mark.asyncio
async def test_due_clic_insieme_sulla_richiesta_una_sola_decisione(repo_ccr):
    rid = await _nuova_richiesta(repo_ccr)
    await apri_connessioni(repo_ccr._pool)
    bot = MagicMock()
    bot.get_user.return_value = None
    bot.fetch_user = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=404, reason="x"), "no"))
    cog = CustomCommandRequestsCog(bot)
    i1 = fake_interaction(user=_staff(10))
    i2 = fake_interaction(user=_staff(11))

    await asyncio.gather(
        cog._handle_decision(i1, rid, APPROVED),
        cog._handle_decision(i2, rid, REJECTED),
    )

    assert i1.response.edit_message.await_count + i2.response.edit_message.await_count == 1
    assert i1.response.send_message.await_count + i2.response.send_message.await_count == 1


@pytest.mark.asyncio
async def test_richiesta_con_invio_fallito_non_resta_orfana(repo_ccr, monkeypatch):
    canale = fake_text_channel(channel_id=60)
    canale.__class__ = discord.TextChannel
    canale.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500, reason="x"), "boom"))
    principale = fake_guild(guild_id=77)
    principale.get_channel.return_value = canale
    bot = MagicMock()
    bot.get_guild.return_value = principale
    monkeypatch.setattr(ccr_module.db, "get_guild_setting", AsyncMock(return_value=60))
    interazione = fake_interaction(guild=fake_guild(guild_id=1), user=fake_member(user_id=3))
    cog = CustomCommandRequestsCog(bot)

    await cog.handle_modal_submit(interazione, "/ciao", "descrizione", "/ciao x")

    interazione.response.defer.assert_awaited_once()
    assert await repo_ccr._pool.fetchval("SELECT COUNT(*) FROM custom_command_requests") == 0
    assert "non" in interazione.followup.send.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_suggerimento_perso_all_ultimo_istante_non_modifica_il_messaggio(repo, monkeypatch):
    # get_suggestion vede ancora "in attesa" ma un altro ha già deciso:
    # set_status risponde False e il clic perdente non tocca il messaggio.
    sid = await repo.create_suggestion(1, 2, 3, "idea")
    monkeypatch.setattr(repo, "set_status", AsyncMock(return_value=False))
    cog = SuggestionsCog(bot=MagicMock())
    interazione = fake_interaction(user=_staff(10))

    await cog._handle_decision(interazione, sid, APPROVED)

    interazione.response.edit_message.assert_not_awaited()
    assert "già" in interazione.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_richiesta_persa_all_ultimo_istante_non_modifica_ne_notifica(repo_ccr, monkeypatch):
    rid = await _nuova_richiesta(repo_ccr)
    monkeypatch.setattr(repo_ccr, "set_status", AsyncMock(return_value=False))
    bot = MagicMock()
    bot.fetch_user = AsyncMock()
    cog = CustomCommandRequestsCog(bot)
    interazione = fake_interaction(user=_staff(10))

    await cog._handle_decision(interazione, rid, APPROVED)

    interazione.response.edit_message.assert_not_awaited()
    bot.fetch_user.assert_not_awaited()
    assert "già" in interazione.response.send_message.await_args.args[0]
