"""
tests/test_automod_decisioni.py
===============================
«Decide lo staff» (AMD-047): le sanzioni aspettano un bottone, le azioni leggere partono subito, la decisione
si prende una volta sola, i bottoni sopravvivono al riavvio (custom_id con l'id della riga).
Funzioni coperte: SPEC §6 (AMD-047), D63
"""

import re
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.automod_azioni as M
import core.automod_decisioni as D
from core.automod_regole_logic import azioni_da_json
from core.repositories.automod_decisioni_repo import automod_decisioni_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_role, fake_text_channel

G = 666


@pytest.fixture
def db(clean_db, monkeypatch):
    monkeypatch.setattr(automod_decisioni_repo, "_pool_provider", lambda: clean_db)
    M._sospese._data.clear()
    M._pause._data.clear()
    monkeypatch.setattr(M.scheduler, "schedule", AsyncMock(return_value=1))
    return clean_db


@pytest.fixture
def log(monkeypatch):
    canale = fake_text_channel(channel_id=77)
    canale.send = AsyncMock(return_value=MagicMock(id=900))
    monkeypatch.setattr(D.router, "destinazione", AsyncMock(return_value=canale))
    return canale


def _bers(membro=None):
    guild = fake_guild(guild_id=G)
    membro = membro or fake_member(user_id=42)
    membro.guild = guild
    msg = fake_message(author=membro, guild=guild, content="contenuto `strano`")
    msg.channel = fake_text_channel(channel_id=10)
    return M.Bersaglio(guild=guild, motivo="Anti-Link", regola_chiave="anti_link", regola_nome="Anti-Link",
                       membro=membro, messaggio=msg, canale=msg.channel)


def A(*dati):
    return azioni_da_json(list(dati))


async def test_le_sanzioni_aspettano_e_le_azioni_leggere_partono(db, log, monkeypatch):
    b = _bers()
    isola, cancella = AsyncMock(), AsyncMock()
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    monkeypatch.setattr(M.bot_roles, "cancella_messaggio", cancella)
    fatte = await M.esegui_azioni(A({"t": "cancella"}, {"t": "timeout", "secondi": 60}, {"t": "decide_staff"}), b)
    assert fatte == ("delete", "decide_staff")
    isola.assert_not_awaited()
    cancella.assert_awaited_once()
    riga = await db.fetchrow("SELECT * FROM automod_decisioni")
    assert riga["stato"] == "attesa" and riga["user_id"] == 42 and riga["messaggio_id"] == 900
    assert "strano" in riga["estratto"]
    inviato = log.send.await_args.kwargs
    assert [i.custom_id for i in inviato["view"].children] == [f"amdec:ok:{riga['id']}", f"amdec:no:{riga['id']}"]
    assert "timeout" in inviato["embed"].fields[1].value
    assert "`strano`" not in inviato["embed"].fields[2].value  # l'estratto non rompe il codice del riquadro


async def test_chi_e_protetto_non_apre_nessuna_decisione(db, log):
    admin = fake_member(user_id=7, guild_permissions=discord.Permissions(administrator=True))
    fatte = await M.esegui_azioni(A({"t": "timeout", "secondi": 60}, {"t": "decide_staff"}), _bers(admin))
    assert fatte == ()
    assert await db.fetchval("SELECT count(*) FROM automod_decisioni") == 0
    log.send.assert_not_awaited()


async def test_senza_canale_del_log_nessuna_sanzione_e_nessuna_riga(db, monkeypatch):
    monkeypatch.setattr(D.router, "destinazione", AsyncMock(return_value=None))
    isola = AsyncMock()
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    assert await M.esegui_azioni(A({"t": "timeout", "secondi": 60}, {"t": "decide_staff"}), _bers()) == ()
    isola.assert_not_awaited()
    assert await db.fetchval("SELECT count(*) FROM automod_decisioni") == 0


async def test_regola_senza_sanzioni_non_chiede_niente(db, log, monkeypatch):
    monkeypatch.setattr(M.bot_roles, "cancella_messaggio", AsyncMock())
    assert await M.esegui_azioni(A({"t": "cancella"}, {"t": "decide_staff"}), _bers()) == ("delete",)
    log.send.assert_not_awaited()


def _click(guild, staff_perms, membro):
    inter = fake_interaction(guild=guild, user=fake_member(user_id=900, guild_permissions=staff_perms))
    inter.user.display_name = "Mod"
    inter.message = MagicMock(embeds=[discord.Embed(title="x")])
    inter.edit_original_response = AsyncMock()
    guild.get_member = MagicMock(return_value=membro)
    guild.get_channel = MagicMock(return_value=None)
    return inter


async def _crea(db, log, monkeypatch):
    b = _bers()
    monkeypatch.setattr(M.bot_roles, "cancella_messaggio", AsyncMock())
    await M.esegui_azioni(A({"t": "timeout", "secondi": 900}, {"t": "decide_staff"}), b)
    return b, await db.fetchval("SELECT id FROM automod_decisioni")


async def test_applica_esegue_le_sanzioni_una_volta_sola(db, log, monkeypatch):
    b, did = await _crea(db, log, monkeypatch)
    isola = AsyncMock()
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    mod = discord.Permissions(moderate_members=True)
    uno, due = _click(b.guild, mod, b.membro), _click(b.guild, mod, b.membro)
    await D.decidi(uno, did, "ok")
    await D.decidi(due, did, "ok")  # il secondo arriva tardi
    isola.assert_awaited_once()
    assert isola.await_args.args[1].total_seconds() == 900
    assert "già deciso" in due.response.send_message.await_args.args[0]
    riga = await db.fetchrow("SELECT stato, decisa_da FROM automod_decisioni")
    assert (riga["stato"], riga["decisa_da"]) == ("applicata", 900)
    nuova = uno.edit_original_response.await_args.kwargs["view"]
    assert all(i.item.disabled for i in nuova.children)


async def test_ignora_non_sanziona_e_senza_permesso_non_si_decide(db, log, monkeypatch):
    b, did = await _crea(db, log, monkeypatch)
    isola = AsyncMock()
    monkeypatch.setattr(M.bot_roles, "isola", isola)
    senza = _click(b.guild, discord.Permissions.none(), b.membro)
    await D.decidi(senza, did, "ok")
    assert "permesso" in senza.response.send_message.await_args.args[0]
    assert await db.fetchval("SELECT stato FROM automod_decisioni") == "attesa"
    await D.decidi(_click(b.guild, discord.Permissions(moderate_members=True), b.membro), did, "no")
    isola.assert_not_awaited()
    assert await db.fetchval("SELECT stato FROM automod_decisioni") == "ignorata"


async def test_decisione_di_un_altro_server_non_vale(db, log, monkeypatch):
    b, did = await _crea(db, log, monkeypatch)
    altro = fake_guild(guild_id=G + 1)
    inter = _click(altro, discord.Permissions(administrator=True, moderate_members=True), b.membro)
    await D.decidi(inter, did, "ok")
    assert await db.fetchval("SELECT stato FROM automod_decisioni") == "attesa"


def test_il_bottone_persistente_si_ricostruisce_dal_custom_id():
    m = re.fullmatch(D.MODELLO_ID, "amdec:ok:123")
    assert m and m["esito"] == "ok" and int(m["id"]) == 123
    assert len("amdec:no:9223372036854775807") <= 100
    assert not re.fullmatch(D.MODELLO_ID, "amdec:boh:1")
    assert D.vista(5).timeout is None  # una View persistente non scade
