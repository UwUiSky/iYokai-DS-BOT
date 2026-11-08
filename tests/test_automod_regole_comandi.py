"""
tests/test_automod_regole_comandi.py
====================================
Comandi `/admin-automod regole`, `gruppo` e `immagini`: aprono il pannello, accendono i gruppi, scrivono le
impostazioni immagini_* solo attraverso lo schema.
Funzioni coperte: SPEC §6 (AMD-067), D62, D63
"""

from unittest.mock import AsyncMock, create_autospec

import pytest
from discord import app_commands

import cogs.automod.regole as modulo
import cogs.moderation._shared as condiviso
from core import automod_regole_service as servizio
from core.automod_regole_logic import Regola
from core.database import Database
from core.repositories.automod_advanced_repo import automod_advanced_repo
from core.repositories.automod_regole_repo import automod_regole_repo
from tests.support.discord_fakes import fake_guild, fake_interaction

GID = 666


@pytest.fixture
def cog(clean_db, monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    db_finto.get_guild_setting.return_value = None
    monkeypatch.setattr(condiviso, "db", db_finto)
    monkeypatch.setattr(automod_regole_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    servizio.svuota_cache()
    c = modulo.RegoleCog(bot=None)
    c.db = db_finto
    return c


async def test_regole_apre_il_pannello_e_rifiuta_una_regola_sconosciuta(cog):
    inter = fake_interaction(guild=fake_guild(guild_id=GID))
    await cog.regole.callback(cog, inter, None)
    assert inter.response.send_message.await_args.kwargs["ephemeral"] is True
    assert inter.response.send_message.await_args.kwargs["view"].timeout == 14 * 60
    inter2 = fake_interaction(guild=fake_guild(guild_id=GID))
    await cog.regole.callback(cog, inter2, "inventata")
    assert "view" not in inter2.response.send_message.await_args.kwargs
    inter3 = fake_interaction(guild=fake_guild(guild_id=GID))
    await cog.regole.callback(cog, inter3, "anti_caps")  # un filtro si apre già sulla sua schermata
    assert "anti_caps" in inter3.response.send_message.await_args.kwargs["embed"].title


async def test_gruppo_accende_e_spegne(cog):
    for n in ("a", "b"):
        await servizio.crea_personale(GID, Regola(chiave="x", tipo="personale", nome=n, gruppo="raid"), 1)
    inter = fake_interaction(guild=fake_guild(guild_id=GID))
    await cog.gruppo.callback(cog, inter, "raid", False)
    assert "2" in inter.response.send_message.await_args.args[0]
    assert all(not r.attiva for r in await servizio.regole_del_server(GID))


async def test_immagini_scrive_con_il_setter_del_filtro_e_mostra_lo_stato(cog, monkeypatch):
    chiamate = AsyncMock()
    monkeypatch.setattr(modulo.immagini_opzioni, "imposta", chiamate)
    inter = fake_interaction(guild=fake_guild(guild_id=GID))
    canale = type("C", (), {"id": 777})()
    await cog.immagini.callback(cog, inter, True, app_commands.Choice(name="timeout", value="timeout"), 30, canale)
    chiamate.assert_awaited_once_with(GID, inter.user.id, attivo=True, azione="timeout", timeout_minuti=30, canale_log_id=777)
    chiamate.side_effect = ValueError("azione: cancella, avvisa, timeout.")
    inter2 = fake_interaction(guild=fake_guild(guild_id=GID))
    await cog.immagini.callback(cog, inter2, None, app_commands.Choice(name="x", value="x"), None, None)
    assert "non valido" in inter2.response.send_message.await_args.args[0].lower() or "invalid" in inter2.response.send_message.await_args.args[0].lower()
    # senza opzioni: mostra lo stato
    monkeypatch.setattr(modulo.account_rubato_opzioni, "attivo", AsyncMock(return_value=True))
    monkeypatch.setattr(modulo.immagini_opzioni, "leggi", AsyncMock(return_value=modulo.immagini_opzioni.OpzioniImmagini(
        attivo=True, azione="avvisa", timeout_minuti=15, canale_log_id=5)))
    inter3 = fake_interaction(guild=fake_guild(guild_id=GID))
    await cog.immagini.callback(cog, inter3, None, None, None, None)
    testo = inter3.response.send_message.await_args.args[0]
    assert "avvisa" in testo and "15" in testo and "<#5>" in testo


async def test_immagini_account_rubato_si_scrive_dal_punto_unico_e_si_vede_nello_stato(cog, monkeypatch):
    scrive = AsyncMock()
    monkeypatch.setattr(modulo.account_rubato_opzioni, "imposta", scrive)
    inter = fake_interaction(guild=fake_guild(guild_id=GID))
    await cog.immagini.callback(cog, inter, None, None, None, None, False)
    scrive.assert_awaited_once_with(GID, inter.user.id, False)
    monkeypatch.setattr(modulo.account_rubato_opzioni, "attivo", AsyncMock(return_value=False))
    monkeypatch.setattr(modulo.immagini_opzioni, "leggi", AsyncMock(return_value=modulo.immagini_opzioni.OpzioniImmagini()))
    inter2 = fake_interaction(guild=fake_guild(guild_id=GID))
    await cog.immagini.callback(cog, inter2, None, None, None, None)
    assert "account rubati" in inter2.response.send_message.await_args.args[0]
