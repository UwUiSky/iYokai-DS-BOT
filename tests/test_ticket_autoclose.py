"""
tests/test_ticket_autoclose.py
==============================
NF-13 (#84): chiusura automatica dei ticket fermi, tramite lo scheduler
persistente. Database vero, scheduler vero; Discord finto.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord.ext import commands

import cogs.tickets.tickets as modulo
from cogs.tickets.tickets import TICKET_AUTOCLOSE_ACTION_TYPE, TICKET_DELETE_ACTION_TYPE
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import fake_guild, fake_member, fake_message, fake_text_channel

GUILD_ID = 100
CANALE = 200
UTENTE = 20
BOT_ID = 999


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()


@pytest.fixture
async def cog(monkeypatch):
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    yield bot.get_cog("TicketsCog")
    await bot.close()


@pytest.fixture
def canale(cog, monkeypatch):
    c = fake_text_channel(CANALE)
    c.history.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason="x"), "x")
    guild = fake_guild(GUILD_ID)
    guild.me = fake_member(BOT_ID)
    guild.get_member.return_value = None
    c.guild = guild
    monkeypatch.setattr(cog.bot, "get_channel", lambda cid: c if cid == CANALE else None)
    cog.bot.fetch_user = AsyncMock(side_effect=discord.NotFound(SimpleNamespace(status=404, reason="x"), "x"))
    return c


async def _ticket(minuti_attivita_fa: int, autoclose=30, voto=False):
    p = await ticket_form_repo.crea_pannello(GUILD_ID, "Supporto", 1, "Supporto")
    if autoclose:
        await ticket_form_repo.imposta_chiusura_automatica(p.id, autoclose)
    if voto:
        await ticket_form_repo.imposta_voto(p.id, True)
    await ticket_repo.create_ticket(GUILD_ID, UTENTE, CANALE, ticket_number=1, panel_id=p.id)
    await ticket_repo._pool.execute(
        "UPDATE tickets SET last_activity_at = $1 WHERE channel_id = $2",
        datetime.now(timezone.utc) - timedelta(minutes=minuti_attivita_fa),
        CANALE,
    )
    return p


async def _azioni(pool, tipo):
    return await pool.fetch("SELECT * FROM scheduled_actions WHERE action_type = $1", tipo)


async def test_ticket_fermo_da_piu_di_n_minuti_si_chiude_e_il_canale_va_allo_scheduler(cog, canale, clean_db):
    await _ticket(45, autoclose=30)
    await cog.handle_ticket_autoclose(GUILD_ID, UTENTE, {"channel_id": CANALE})
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    assert t.status == "closed" and t.closed_by == BOT_ID
    assert len(await _azioni(clean_db, TICKET_DELETE_ACTION_TYPE)) == 1
    canale.send.assert_awaited_once()
    canale.delete.assert_not_awaited()  # lo elimina lo scheduler, non questo handler


async def test_ticket_con_attivita_recente_resta_aperto_e_il_controllo_si_sposta(cog, canale, clean_db):
    await _ticket(10, autoclose=30)
    await cog.handle_ticket_autoclose(GUILD_ID, UTENTE, {"channel_id": CANALE})
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "open"
    (azione,) = await _azioni(clean_db, TICKET_AUTOCLOSE_ACTION_TYPE)
    atteso = datetime.now(timezone.utc) + timedelta(minutes=20)
    assert abs((azione["execute_at"] - atteso).total_seconds()) < 60


async def test_pannello_con_chiusura_spenta_nel_frattempo_non_chiude(cog, canale):
    await _ticket(500, autoclose=None)
    await cog.handle_ticket_autoclose(GUILD_ID, UTENTE, {"channel_id": CANALE})
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "open"


async def test_ticket_gia_chiuso_non_viene_toccato(cog, canale, clean_db):
    await _ticket(500)
    await ticket_repo.close_ticket(CANALE, 5)
    await cog.handle_ticket_autoclose(GUILD_ID, UTENTE, {"channel_id": CANALE})
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).closed_by == 5
    assert await _azioni(clean_db, TICKET_DELETE_ACTION_TYPE) == []


async def test_alla_chiusura_automatica_parte_il_voto_se_acceso(cog, canale):
    await _ticket(45, voto=True)
    utente = fake_member(UTENTE)
    utente.send = AsyncMock()
    canale.guild.get_member.return_value = utente
    await cog.handle_ticket_autoclose(GUILD_ID, UTENTE, {"channel_id": CANALE})
    utente.send.assert_awaited()
    assert any("view" in c.kwargs for c in utente.send.await_args_list)


async def test_un_messaggio_tiene_vivo_il_ticket_ma_si_scrive_al_massimo_una_volta_al_minuto(cog, canale):
    await _ticket(45)
    msg = fake_message(channel=canale, author=fake_member(UTENTE))
    msg.guild = canale.guild
    msg.author.bot = False
    await cog.on_message(msg)
    prima = (await ticket_repo.get_ticket_by_channel(CANALE)).last_activity_at
    assert datetime.now(timezone.utc) - prima < timedelta(minutes=1)
    # secondo messaggio subito dopo: nessuna nuova scrittura
    await ticket_repo._pool.execute(
        "UPDATE tickets SET last_activity_at = $1 WHERE channel_id = $2", prima - timedelta(hours=1), CANALE
    )
    await cog.on_message(msg)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).last_activity_at < prima


async def test_i_messaggi_del_bot_non_tengono_vivo_il_ticket(cog, canale):
    await _ticket(45)
    msg = fake_message(channel=canale, author=fake_member(BOT_ID))
    msg.guild = canale.guild
    msg.author.bot = True
    await cog.on_message(msg)
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    assert datetime.now(timezone.utc) - t.last_activity_at > timedelta(minutes=40)


async def test_utente_che_esce_dal_server_chiude_il_suo_ticket(cog, canale, clean_db):
    await _ticket(1, autoclose=None)
    canale.guild.get_channel.return_value = canale
    utente = fake_member(UTENTE)
    utente.guild = canale.guild
    await cog.on_member_remove(utente)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "closed"
    assert len(await _azioni(clean_db, TICKET_DELETE_ACTION_TYPE)) == 1
    canale.send.assert_awaited_once()


async def test_uscita_di_un_utente_senza_ticket_non_fa_nulla(cog, canale):
    utente = fake_member(UTENTE)
    utente.guild = canale.guild
    await cog.on_member_remove(utente)
    canale.send.assert_not_awaited()
