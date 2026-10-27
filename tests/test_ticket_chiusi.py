"""
tests/test_ticket_chiusi.py
===========================
#120 TKT-051, 063, 027, 026: chiusura in due passi (il canale resta, chiuso), eliminazione
dopo N ore, categoria dei chiusi, prefissi del nome. Database vero; Discord finto.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.tickets.tickets as modulo
from cogs.tickets.tickets import TICKET_DELETE_ACTION_TYPE
from core import ticket_opzioni_logic as logica
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

GUILD_ID = 100
CANALE = 200
UTENTE = 20
MANAGER = 31
CATEGORIA_CHIUSI = 900


@pytest.fixture(autouse=True)
async def _pool(monkeypatch, clean_db):
    await clean_db.execute("DELETE FROM scheduled_actions")
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    ticket_opzioni_repo._cache.clear()
    import core.channel_rename as rinomina

    rinomina.rename_tracker._renames.clear()


@pytest.fixture
async def cog(monkeypatch):
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    c = bot.get_cog("TicketsCog")
    c._transcript_senza_bloccare = AsyncMock()
    c._richiedi_voto = AsyncMock()
    yield c
    await bot.close()


async def _pannello_con_ticket(**opzioni):
    panel = await ticket_form_repo.crea_pannello(GUILD_ID, "Supporto", 1, "Supporto")
    await ticket_opzioni_repo.imposta(panel.id, **opzioni)
    await ticket_repo.create_ticket(GUILD_ID, UTENTE, CANALE, ticket_number=1, panel_id=panel.id)
    return panel


def _scena():
    guild = fake_guild(GUILD_ID)
    utente = fake_member(UTENTE)
    manager = fake_member(MANAGER, guild_permissions=discord.Permissions(manage_guild=True))
    guild.get_member.side_effect = {UTENTE: utente, MANAGER: manager}.get
    categoria = MagicMock(spec=discord.CategoryChannel)
    categoria.channels = []
    guild.get_channel.side_effect = {CATEGORIA_CHIUSI: categoria}.get
    canale = fake_text_channel(CANALE, "ticket-0001")
    canale.guild = guild
    canale.category_id = 1
    canale.overwrites_for.return_value = discord.PermissionOverwrite()
    canale.send = AsyncMock()
    canale.set_permissions = AsyncMock()
    canale.edit = AsyncMock()
    return guild, canale, utente, manager


def _inter(guild, canale, user):
    return fake_interaction(guild=guild, user=user, channel=canale)


async def _azioni_di_eliminazione(clean_db):
    return await clean_db.fetch("SELECT * FROM scheduled_actions WHERE action_type = $1", TICKET_DELETE_ACTION_TYPE)


async def test_senza_i_due_passi_il_canale_si_elimina_a_breve_come_prima(cog, clean_db):
    await _pannello_con_ticket()
    guild, canale, utente, _ = _scena()
    i = _inter(guild, canale, utente)
    await cog.close.callback(cog, i, None)
    assert len(await _azioni_di_eliminazione(clean_db)) == 1
    assert "eliminato" in str(i.response.send_message.call_args)
    canale.send.assert_not_awaited()


async def test_due_passi_il_canale_resta_con_i_bottoni_e_l_utente_non_lo_vede(cog, clean_db):
    await _pannello_con_ticket(
        chiusura_due_passi=True, categoria_chiusi=CATEGORIA_CHIUSI, prefisso_chiuso="chiuso"
    )
    guild, canale, utente, _ = _scena()
    i = _inter(guild, canale, utente)
    await cog.close.callback(cog, i, "Fatto")
    assert await _azioni_di_eliminazione(clean_db) == []
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "closed"
    # l'utente perde la vista; il canale va nella categoria dei chiusi e cambia nome
    ow = canale.set_permissions.await_args.kwargs["overwrite"]
    assert ow.view_channel is False
    canale.edit.assert_any_await(
        category=guild.get_channel(CATEGORIA_CHIUSI), sync_permissions=False, reason="Ticket chiuso"
    )
    canale.edit.assert_any_await(name="chiuso-ticket-0001", reason="Ticket chiuso")
    vista = canale.send.await_args.kwargs["view"]
    assert [b.item.label for b in vista.children] == ["Riapri", "Transcript", "Elimina"]


async def test_elimina_dopo_n_ore_pianifica_l_eliminazione_nel_futuro(cog, clean_db):
    await _pannello_con_ticket(chiusura_due_passi=True, elimina_dopo_ore=24)
    guild, canale, utente, _ = _scena()
    await cog.close.callback(cog, _inter(guild, canale, utente), None)
    azioni = await _azioni_di_eliminazione(clean_db)
    assert len(azioni) == 1
    ritardo = await clean_db.fetchval(
        "SELECT extract(epoch FROM execute_at - now()) FROM scheduled_actions WHERE action_type = $1",
        TICKET_DELETE_ACTION_TYPE,
    )
    assert 23 * 3600 < ritardo <= 24 * 3600


async def test_riapri_ridona_l_accesso_e_il_canale_non_si_elimina_piu(cog, clean_db):
    await _pannello_con_ticket(chiusura_due_passi=True, elimina_dopo_ore=1, prefisso_chiuso="chiuso")
    guild, canale, utente, manager = _scena()
    await cog.close.callback(cog, _inter(guild, canale, utente), None)
    canale.name = "chiuso-ticket-0001"
    canale.set_permissions.reset_mock()
    ticket = await ticket_repo.get_ticket_by_channel(CANALE)

    esito = await cog._riapri(guild, canale, ticket, manager)

    assert esito == "Ticket riaperto."
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "open"
    assert canale.set_permissions.await_args.kwargs["overwrite"].view_channel is True
    canale.edit.assert_any_await(name="ticket-0001", reason="Ticket riaperto")
    # l'eliminazione già pianificata arriva e non fa nulla
    cog._elimina_canale = AsyncMock()
    await cog.handle_ticket_delete_channel(GUILD_ID, UTENTE, {"channel_id": CANALE, "reason": "x"})
    cog._elimina_canale.assert_not_awaited()


async def test_riapri_non_va_se_l_utente_ha_gia_un_altro_ticket_aperto(cog):
    await _pannello_con_ticket(chiusura_due_passi=True)
    guild, canale, utente, manager = _scena()
    await cog.close.callback(cog, _inter(guild, canale, utente), None)
    await ticket_repo.create_ticket(GUILD_ID, UTENTE, 201, ticket_number=2)
    ticket = await ticket_repo.get_ticket_by_channel(CANALE)

    esito = await cog._riapri(guild, canale, ticket, manager)

    assert "massimo" in esito
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "closed"


async def test_i_bottoni_del_ticket_chiuso_sono_per_lo_staff(cog):
    await _pannello_con_ticket(chiusura_due_passi=True)
    guild, canale, utente, manager = _scena()
    await cog.close.callback(cog, _inter(guild, canale, utente), None)
    ticket = await ticket_repo.get_ticket_by_channel(CANALE)
    bottone = modulo.BottoneChiuso(ticket.id, "e")

    i = _inter(guild, canale, utente)
    i.client = MagicMock()
    i.client.get_cog.return_value = cog
    await bottone.callback(i)
    assert "Solo lo staff" in str(i.response.send_message.call_args)

    cog._elimina_canale = AsyncMock()
    i = _inter(guild, canale, manager)
    i.client = MagicMock()
    i.client.get_cog.return_value = cog
    await bottone.callback(i)
    cog._elimina_canale.assert_awaited_once()


async def test_il_prefisso_alla_presa_in_carico(cog):
    await _pannello_con_ticket(prefisso_preso="preso")
    guild, canale, utente, manager = _scena()
    ticket = await ticket_repo.get_ticket_by_channel(CANALE)
    await cog._dopo_presa(guild, canale, ticket, manager)
    canale.edit.assert_awaited_with(name="preso-ticket-0001", reason="Ticket preso in carico")


def test_nome_con_prefisso_sostituisce_i_prefissi_noti():
    assert logica.nome_con_prefisso("ticket-1", "Chiuso") == "chiuso-ticket-1"
    assert logica.nome_con_prefisso("preso-ticket-1", "chiuso", ("preso", "chiuso")) == "chiuso-ticket-1"
    assert logica.nome_con_prefisso("chiuso-ticket-1", None, ("preso", "chiuso")) == "ticket-1"
    assert len(logica.nome_con_prefisso("a" * 100, "chiuso")) == 100
    assert logica.prefisso_valido("chiuso") and not logica.prefisso_valido("!!!")
