"""
tests/test_user_app_impostazioni.py
===================================
SPEC B.10, D.7 (#107): impostazioni personali e storico dei comandi di iYokai App.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

import cogs.user_app.impostazioni as imp
from core.repositories.user_app_repo import UserAppRepository
from tests.support.discord_fakes import fake_interaction, fake_member


@pytest.fixture
def cog(monkeypatch, clean_db):
    repo = UserAppRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(imp, "user_app_repo", repo)
    from core.repositories.user_language_repo import user_language_repo

    monkeypatch.setattr(user_language_repo, "_pool_provider", lambda: clean_db)
    c = imp.ImpostazioniCog(MagicMock())
    c.repo = repo
    return c


def _i(user_id=7, guild_id=None):
    i = fake_interaction(user=fake_member(user_id=user_id))
    i.guild_id = guild_id
    return i


def _testo(i):
    return i.response.send_message.await_args.args[0]


async def test_mostra_parte_dai_valori_prudenti(cog):
    i = _i()
    await cog.mostra.callback(cog, i)
    d = i.response.send_message.await_args.kwargs["embed"].description
    assert "solo tu le vedi" in d and "Storico dei comandi:** no" in d and "visibile agli altri:** no" in d


@pytest.mark.parametrize("comando, argomento, campo, valore", [
    ("risposte", False, "risposte_private", False),
    ("dm", False, "dm_ok", False),
    ("storico_acceso", True, "storico", True),
    ("profilo", True, "profilo_pubblico", True),
])
async def test_ogni_impostazione_si_salva(cog, comando, argomento, campo, valore):
    i = _i()
    await getattr(cog, comando).callback(cog, i, argomento)
    assert "Fatto" in _testo(i)
    assert getattr(await cog.repo.impostazioni(7), campo) is valore
    assert getattr(await cog.repo.impostazioni(8), campo) is not valore or comando == "risposte"  # un altro utente non cambia


async def test_lingua_personale(cog):
    i = _i()
    await cog.lingua.callback(cog, i, app_commands.Choice(name="English", value="en"))
    assert "`en`" in _testo(i)
    i = _i()
    await cog.lingua.callback(cog, i, app_commands.Choice(name="Server", value="server"))
    assert "tolta" in _testo(i) or "removed" in _testo(i)


async def test_lo_storico_si_salva_solo_se_acceso_e_non_salva_se_stesso(cog):
    comando = MagicMock(spec=app_commands.Command)
    comando.qualified_name = "strumenti calcola"
    await cog.on_app_command_completion(_i(7, 55), comando)
    assert await cog.repo.storico(7) == []  # spento: niente

    await cog.repo.imposta(7, "storico", True)
    await cog.on_app_command_completion(_i(7, 55), comando)
    menu = MagicMock(spec=app_commands.ContextMenu)
    menu.name = "Traduci"
    await cog.on_app_command_completion(_i(7, None), menu)
    sul_storico = MagicMock(spec=app_commands.Command)
    sul_storico.qualified_name = "storico elenco"
    await cog.on_app_command_completion(_i(7, None), sul_storico)
    righe = await cog.repo.storico(7)
    assert [(r["comando"], r["guild_id"]) for r in righe] == [("Traduci", None), ("/strumenti calcola", 55)]


async def test_elenco_azzera_e_spegnere_cancella(cog):
    i = _i()
    await cog.elenco.callback(cog, i)
    assert "spento" in _testo(i)
    await cog.repo.imposta(7, "storico", True)
    i = _i()
    await cog.elenco.callback(cog, i)
    assert "vuoto" in _testo(i)
    await cog.repo.registra_comando(7, "/promemoria crea", None)
    await cog.repo.registra_comando(7, "/note elenco", 9)
    i = _i()
    await cog.elenco.callback(cog, i)
    d = i.response.send_message.await_args.kwargs["embed"].description
    assert "/note elenco" in d and "server 9" in d and "DM" in d
    i = _i()
    await cog.azzera.callback(cog, i)
    assert "2 righe" in _testo(i)
    await cog.repo.registra_comando(7, "/x", None)
    await cog.storico_acceso.callback(cog, _i(), False)
    assert await cog.repo.storico(7) == []


async def test_errore_nel_database_non_ferma_il_comando(cog, monkeypatch):
    monkeypatch.setattr(cog.repo, "impostazioni", AsyncMock(side_effect=RuntimeError("db giù")))
    comando = MagicMock(spec=app_commands.Command)
    comando.qualified_name = "x"
    await cog.on_app_command_completion(_i(), comando)  # non solleva
