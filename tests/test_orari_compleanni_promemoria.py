"""
tests/test_orari_compleanni_promemoria.py
=========================================
Catalogo #128 B6 (D69): compleanni dello staff e prossimi, iscritti a un promemoria pubblico, fuso personale e
menu «Orari nel mio fuso».
"""

from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands as ext

import cogs.utility.birthdays as bd
import cogs.utility.lingua as lg
import cogs.utility.orari as orari
import cogs.utility.reminders as rem
from core import orari_logic as O
from core.repositories.birthday_repo import BirthdayRepository
from core.repositories.promemoria_iscritti_repo import PromemoriaIscrittiRepository
from core.repositories.utente_fuso_repo import UtenteFusoRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo


def test_orari_trovati_solo_con_due_punti_o_ampm():
    assert O.trova_orari("ci vediamo alle 18:30 o alle 6pm, non il 12") == [time(18, 30), time(18, 0)]
    assert O.trova_orari("3 pm e 12 am") == [time(15, 0), time(0, 0)]
    assert O.trova_orari("costa 3.50 euro, 25:99, 2026") == []
    assert len(O.trova_orari(" ".join(f"{h}:00" for h in range(20)))) == O.MAX_ORARI


def test_timestamp_nel_fuso_dell_autore():
    roma = O.fuso_da_nome("Europe/Rome", "UTC")
    adesso = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
    ts = O.timestamp_di(time(18, 30), roma, adesso)
    assert datetime.fromtimestamp(ts, timezone.utc).hour == 17  # 18:30 a Roma in novembre = 17:30 UTC
    assert O.righe_orari("alle 18:30", roma, adesso)[0].startswith("`18:30` → <t:")
    assert O.fuso_da_nome("Posto/Inesistente", "Europe/Rome").key == "Europe/Rome"


def test_fusi_completamento_entro_25():
    assert len(O.cerca_fusi("")) == 25 and "Europe/Rome" in O.cerca_fusi("rome")
    assert O.fuso_esiste("Europe/Rome") and not O.fuso_esiste("Marte/Olimpo")


@pytest.mark.asyncio
async def test_compleanni_prossimi_ripartono_da_gennaio_e_restano_a_pagine(clean_db):
    r = BirthdayRepository(pool_provider=lambda: clean_db)
    for uid, g, m in ((1, 5, 11), (2, 20, 11), (3, 1, 1), (4, 9, 11), (5, 2, 12)):
        await r.set_birthday(1, uid, g, m)
    ordine = [u for u, _, _ in await r.prossimi(1, date(2026, 11, 9), 10)]
    assert ordine == [4, 2, 5, 3, 1]  # da oggi (9/11) in avanti, poi si ricomincia da gennaio
    assert [u for u, _, _ in await r.prossimi(1, date(2026, 11, 9), 2, 2)] == [5, 3]
    assert await r.conta(1) == 5


@pytest.mark.asyncio
async def test_compleanno_registrato_dallo_staff_e_poi_dal_membro(clean_db):
    r = BirthdayRepository(pool_provider=lambda: clean_db)
    await r.set_birthday(1, 7, 3, 4, inserito_da=99)
    assert await clean_db.fetchval("SELECT inserito_da FROM birthdays WHERE user_id = 7") == 99
    await r.set_birthday(1, 7, 4, 4)  # lo cambia il membro: non è più dello staff
    assert await clean_db.fetchval("SELECT inserito_da FROM birthdays WHERE user_id = 7") is None


@pytest.mark.asyncio
async def test_comando_staff_rifiuta_bot_e_date_impossibili(monkeypatch):
    c = bd.BirthdaysCog(MagicMock())
    monkeypatch.setattr(c, "_pronto", AsyncMock(return_value=True))
    set_b = AsyncMock()
    monkeypatch.setattr(bd.birthday_repo, "set_birthday", set_b)
    bot_m = MagicMock(spec=discord.Member, bot=True)
    await c.membro.callback(c, fake_interaction(), bot_m, 1, 1)
    umano = MagicMock(spec=discord.Member, bot=False, id=5, mention="<@5>")
    await c.membro.callback(c, fake_interaction(), umano, 31, 2)
    set_b.assert_not_called()
    it = fake_interaction()
    await c.membro.callback(c, it, umano, 29, 2)
    assert set_b.await_args.kwargs["inserito_da"] == it.user.id


@pytest.mark.asyncio
async def test_iscritti_tetto_25_e_pulizia(clean_db):
    r = PromemoriaIscrittiRepository(pool_provider=lambda: clean_db)
    for u in range(25):
        assert await r.iscrivi("abc123", 1, u) == "ok"
    assert await r.iscrivi("abc123", 1, 3) == "gia"
    assert await r.iscrivi("abc123", 1, 999) == "pieno"
    assert len(await r.iscritti("abc123")) == 25
    await r.cancella_serie("abc123")
    assert await r.iscritti("abc123") == []
    await clean_db.execute("INSERT INTO scheduled_actions (guild_id,user_id,action_type,execute_at,payload) VALUES (1,2,$1,now(),$2::jsonb)", rem.REMINDER_ACTION_TYPE, '{"serie":"zz11aa"}')
    assert await r.serie_attiva("zz11aa", rem.REMINDER_ACTION_TYPE) and not await r.serie_attiva("nope", rem.REMINDER_ACTION_TYPE)


@pytest.mark.asyncio
async def test_fuso_utente_roundtrip(clean_db):
    r = UtenteFusoRepository(pool_provider=lambda: clean_db)
    assert await r.get(5) is None
    await r.set(5, "Europe/Rome"); await r.set(5, "Asia/Tokyo")
    assert await r.get(5) == "Asia/Tokyo" and await r.remove(5) and not await r.remove(5)


def test_custom_id_del_bottone_ricorda():
    b = rem.BottoneRicordaAnche("a1b2c3d4e5f6")
    assert rem.BottoneRicordaAnche.__discord_ui_compiled_template__.match(b.item.custom_id) and len(b.item.custom_id) < 100


@pytest.mark.asyncio
async def test_promemoria_nel_canale_e_pubblico_con_bottone_senza_menzioni(monkeypatch):
    c = rem.RemindersCog(MagicMock())
    monkeypatch.setattr(rem.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    monkeypatch.setattr(rem.scheduler, "list_pending_for_user", AsyncMock(return_value=[]))
    pianifica = AsyncMock(return_value=5)
    monkeypatch.setattr(rem.scheduler, "schedule", pianifica)
    canale = MagicMock()
    canale.permissions_for.return_value = discord.Permissions(send_messages=True)
    canale.id = 9
    it = fake_interaction(channel=canale)
    await c.set_reminder.callback(c, it, "1h", "ciao @everyone", None, True)
    kw = it.response.send_message.await_args.kwargs
    assert not kw.get("ephemeral") and kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].users is False
    assert len(kw["view"].children) == 1
    assert pianifica.await_args.kwargs["payload"]["serie"]


@pytest.mark.asyncio
async def test_scatto_menziona_gli_iscritti_ancora_nel_server(monkeypatch):
    c = rem.RemindersCog(MagicMock())
    canale = MagicMock(spec=discord.TextChannel)
    canale.send = AsyncMock()
    server = fake_guild()
    server.get_channel = lambda _i: canale
    server.get_member = lambda u: object() if u in (1, 2, 3) else None
    c.bot.get_guild.return_value = server
    monkeypatch.setattr(rem.promemoria_iscritti_repo, "iscritti", AsyncMock(return_value=[2, 3, 4]))  # 4 è uscito
    pulisci = AsyncMock()
    monkeypatch.setattr(rem.promemoria_iscritti_repo, "cancella_serie", pulisci)
    await c.handle_reminder_fire(5, 1, {"message": "x", "nel_canale": True, "channel_id": 7, "serie": "abc123"})
    testo = canale.send.await_args.args[0]
    assert "<@1>" in testo and "<@2>" in testo and "<@3>" in testo and "<@4>" not in testo
    assert canale.send.await_args.kwargs["allowed_mentions"].roles is False
    pulisci.assert_awaited_once_with("abc123")  # non si ripete: gli iscritti si cancellano


@pytest.mark.asyncio
async def test_fuso_su_lingua_valida_e_salva(monkeypatch):
    c = lg.LinguaCog(MagicMock())
    salva = AsyncMock()
    monkeypatch.setattr(lg.utente_fuso_repo, "set", salva)
    monkeypatch.setattr(lg, "lingua_server", AsyncMock(return_value="it"))
    monkeypatch.setattr(lg, "lingua_interazione", AsyncMock(return_value="it"))
    it = fake_interaction()
    await c.lingua.callback(c, it, None, "Europe/Rome")
    salva.assert_awaited_once_with(it.user.id, "Europe/Rome")
    salva.reset_mock()
    await c.lingua.callback(c, fake_interaction(), None, "Marte/Olimpo")
    salva.assert_not_called()


@pytest.mark.asyncio
async def test_menu_orari_usa_il_fuso_dell_autore(monkeypatch):
    c = orari.OrariCog(MagicMock())
    monkeypatch.setattr(orari.utente_fuso_repo, "get", AsyncMock(return_value="Asia/Tokyo"))
    msg = MagicMock(content="partita alle 21:00")
    msg.author.id = 3
    it = fake_interaction()
    await c.menu_orari(it, msg)
    testo = it.response.send_message.await_args.args[0]
    assert "Asia/Tokyo" in testo and "`21:00`" in testo
    it2 = fake_interaction()
    msg.content = "niente orari qui"
    await c.menu_orari(it2, msg)
    assert it2.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_albero_nuovi_comandi_e_menu():
    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await bd.setup(bot)
    await lg.setup(bot)
    await orari.setup(bot)
    assert comando_nel_gruppo("level", "compleanno prossimi") and comando_nel_gruppo("admin-moduli", "compleanni membro")
    m = comando_nel_gruppo("level", "compleanno mostra").to_dict(bot.tree)["options"]
    assert [o["name"] for o in m] == ["membro"] and not m[0].get("required")
    f = comando_nel_gruppo("utility", "lingua").to_dict(bot.tree)["options"]
    assert f[-1]["name"] == "fuso" and f[-1]["max_length"] == 60 and f[-1]["autocomplete"]
    assert bot.tree.get_command(orari.NOME_MENU, type=discord.AppCommandType.message) is not None
