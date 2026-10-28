"""
tests/test_automod_parole_odio.py
=================================
AMD-014 nei cog: il messaggio con una parola vietata (anche camuffata) viene
cancellato, conta nella scala di escalation e finisce nel log; liste e
conferma per spegnere la base; nomi ripuliti all'ingresso e al cambio.
Database vero; messaggi, membri e bot finti fedeli.
"""

from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.automod.automod as modulo_automod
import cogs.automod.escalation as modulo_escalation
import cogs.automod.parole_odio as modulo_parole
import cogs.moderation._shared as modulo_shared
import core.database as modulo_database
from core import automod_parole_opzioni as opz
from core.automod_parole_logic import costruisci
from core.automod_rate_tracker import AutomodRateTracker
from core.database import Database, db
from core.repositories.automod_advanced_repo import automod_advanced_repo
from core.repositories.escalation_repo import escalation_repo
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
)
from tests.support.router_fakes import router_senza_scelte

GUILD_ID = 666
AUTORE_ID = 4242
CAMUFFATA = "ciao n1gg3r"


def _impostazioni(monkeypatch, **valori):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    db_finto.get_guild_setting.side_effect = lambda gid, chiave, default=None: valori.get(chiave, default)
    monkeypatch.setattr(modulo_shared, "db", db_finto)
    monkeypatch.setattr(modulo_automod, "db", db_finto)


@pytest.fixture
def cog(clean_db, monkeypatch):
    _impostazioni(monkeypatch)
    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    router_senza_scelte(monkeypatch)
    monkeypatch.setattr(modulo_automod, "rate_tracker", AutomodRateTracker())
    return modulo_automod.AutomodCog(bot=MagicMock())


def _messaggio(contenuto, ruoli=None):
    server = fake_guild(guild_id=GUILD_ID)
    autore = fake_member(user_id=AUTORE_ID, roles=ruoli)
    autore.guild = server
    messaggio = fake_message(author=autore, guild=server, content=contenuto)
    messaggio.channel = fake_text_channel(channel_id=111)
    messaggio.mentions, messaggio.role_mentions = [], []
    messaggio.mention_everyone = False
    messaggio.attachments, messaggio.stickers = [], []
    return messaggio


async def _violazioni():
    return [r["violation"] for r in await automod_advanced_repo.get_recent_actions(GUILD_ID)]


async def test_messaggio_camuffato_viene_cancellato_e_registrato(cog):
    sporco, pulito = _messaggio(CAMUFFATA), _messaggio("ciao a tutti, il Niger e in Africa")
    await cog.on_message(sporco)
    await cog.on_message(pulito)
    sporco.delete.assert_awaited_once()
    pulito.delete.assert_not_awaited()
    assert await _violazioni() == ["parole_vietate"]
    cog.bot.dispatch.assert_called_once_with("automod_parole_vietate", sporco)


async def test_messaggio_modificato_viene_controllato(cog):
    prima, dopo = _messaggio("ciao"), _messaggio(CAMUFFATA)
    await cog.on_message_edit(prima, dopo)
    dopo.delete.assert_awaited_once()


async def test_base_spenta_non_blocca(clean_db, monkeypatch, cog):
    _impostazioni(monkeypatch, automod_parole_base=False)
    messaggio = _messaggio(CAMUFFATA)
    await cog.on_message(messaggio)
    messaggio.delete.assert_not_awaited()


async def test_parola_propria_con_stesse_normalizzazioni(clean_db, monkeypatch, cog):
    _impostazioni(monkeypatch, automod_parole_base=False, automod_parole_proprie=["scemo"])
    sporco = _messaggio("sei uno sc3m0")
    await cog.on_message(sporco)
    sporco.delete.assert_awaited_once()


async def test_parola_lecita_dell_admin_non_scatta(clean_db, monkeypatch, cog):
    _impostazioni(monkeypatch, automod_parole_lecite=["negro"])
    messaggio = _messaggio("il fiume rio negro")
    await cog.on_message(messaggio)
    messaggio.delete.assert_not_awaited()


async def test_ruolo_esente_non_viene_controllato(cog):
    ruolo = fake_role(role_id=77)
    await cog.exempt_role_add.callback(cog, fake_interaction(guild=fake_guild(guild_id=GUILD_ID)), ruolo)
    messaggio = _messaggio(CAMUFFATA, ruoli=[ruolo])
    await cog.on_message(messaggio)
    messaggio.delete.assert_not_awaited()


# --- Scala di escalation -------------------------------------------------
@pytest.fixture
async def escalation(clean_db, monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo_escalation, "db", db_finto)
    monkeypatch.setattr(escalation_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(moderation_repo, "_pool_provider", lambda: clean_db)
    bot = create_autospec(commands.Bot, instance=True)
    bot.user = fake_member(user_id=999, bot=True)
    await escalation_repo.set_enabled(GUILD_ID, True)
    return modulo_escalation.EscalationCog(bot)


async def _conteggio(pool):
    return await pool.fetchval(
        "SELECT violation_count FROM automod_violations WHERE guild_id = $1 AND user_id = $2", GUILD_ID, AUTORE_ID
    )


async def test_parola_vietata_conta_una_infrazione_una_volta_sola(escalation, clean_db):
    messaggio = _messaggio(CAMUFFATA)
    await escalation.on_automod_parole_vietate(messaggio)
    await escalation.on_automod_parole_vietate(messaggio)  # stesso messaggio: non conta due volte
    assert await _conteggio(clean_db) == 1


async def test_scala_spenta_non_conta(escalation, clean_db):
    await escalation_repo.set_enabled(GUILD_ID, False)
    await escalation.on_automod_parole_vietate(_messaggio(CAMUFFATA))
    assert await _conteggio(clean_db) is None


# --- Impostazioni --------------------------------------------------------
@pytest.fixture
async def archivio(clean_db, monkeypatch):
    monkeypatch.setattr(modulo_database.db, "_pool", clean_db)
    modulo_database.db._settings_cache.clear()
    yield
    modulo_database.db._settings_cache.clear()


async def test_spegnere_la_base_chiede_conferma(archivio):
    with pytest.raises(ValueError):
        await opz.imposta_base(GUILD_ID, False, False, 1)
    assert (await opz.leggi(GUILD_ID)).base is True
    await opz.imposta_base(GUILD_ID, False, True, 1)
    assert (await opz.leggi(GUILD_ID)).base is False
    assert await opz.trova_nel_testo(GUILD_ID, "n1gg3r") is None


async def test_liste_proprie_e_lecite(archivio):
    assert await opz.aggiungi_voce(GUILD_ID, opz.LISTA_PROPRIE, "scemo", 1) is True
    assert await opz.aggiungi_voce(GUILD_ID, opz.LISTA_PROPRIE, "SCEMO", 1) is False
    assert await opz.trova_nel_testo(GUILD_ID, "s c e m o") is not None
    assert await opz.rimuovi_voce(GUILD_ID, opz.LISTA_PROPRIE, "scemo", 1) is True
    assert await opz.trova_nel_testo(GUILD_ID, "s c e m o") is None
    await opz.aggiungi_voce(GUILD_ID, opz.LISTA_LECITE, "negro", 1)
    assert await opz.trova_nel_testo(GUILD_ID, "rio negro") is None
    with pytest.raises(ValueError):
        await opz.aggiungi_voce(GUILD_ID, opz.LISTA_PROPRIE, "ab", 1)


async def test_lista_piena_rifiuta(archivio):
    for numero in range(opz.MAX_VOCI):
        await opz.aggiungi_voce(GUILD_ID, opz.LISTA_PROPRIE, f"parola{'x' * (numero % 20)}{numero}", 1)
    with pytest.raises(ValueError):
        await opz.aggiungi_voce(GUILD_ID, opz.LISTA_PROPRIE, "ancora", 1)


async def test_comando_base_senza_conferma_non_spegne(archivio, monkeypatch):
    monkeypatch.setattr(modulo_parole, "ensure_module_enabled", lambda i, m: _vero())
    cog = modulo_parole.ParoleOdioCog(MagicMock())
    interazione = fake_interaction(guild=fake_guild(guild_id=GUILD_ID))
    await cog.base.callback(cog, interazione, False, False)
    assert (await opz.leggi(GUILD_ID)).base is True
    await cog.base.callback(cog, interazione, False, True)
    assert (await opz.leggi(GUILD_ID)).base is False


async def _vero():
    return True


# --- Nomi ----------------------------------------------------------------
def test_nuovo_nick():
    f = costruisci(True)
    assert modulo_parole.nuovo_nick("n1gg3r", "Mario", f) == (True, None)
    assert modulo_parole.nuovo_nick("n1gg3r", "n i g g e r", f) == (True, modulo_parole.NOME_SOSTITUTIVO)
    assert modulo_parole.nuovo_nick("Mario", "n1gg3r", f) == (False, None)
    assert modulo_parole.nuovo_nick(None, "n1gg3r", f) == (True, modulo_parole.NOME_SOSTITUTIVO)
    assert modulo_parole.nuovo_nick(None, "Mario", f) == (False, None)


@pytest.fixture
async def ambiente_nomi(clean_db, archivio, monkeypatch):
    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    router_senza_scelte(monkeypatch)
    await db.set_module_active_for_guild(GUILD_ID, modulo_automod.MODULE_AUTOMOD, True)


def _membro(nick, nome="Mario"):
    server = fake_guild(guild_id=GUILD_ID, owner_id=1)
    membro = fake_member(user_id=AUTORE_ID, name=nome)
    membro.guild, membro.nick, membro.global_name = server, nick, nome
    return membro


async def test_nome_vietato_all_ingresso_azzera_il_nickname(ambiente_nomi):
    membro = _membro("n1gg3r")
    assert await modulo_parole.controlla_nome(membro) == "nickname azzerato"
    membro.edit.assert_awaited_once()
    assert membro.edit.await_args.kwargs["nick"] is None


async def test_nome_pulito_non_si_tocca(ambiente_nomi):
    membro = _membro("Mario")
    assert await modulo_parole.controlla_nome(membro) is None
    membro.edit.assert_not_awaited()


async def test_nomi_spenti_non_controlla(ambiente_nomi):
    await opz.imposta_nick(GUILD_ID, False, 1)
    membro = _membro("n1gg3r")
    assert await modulo_parole.controlla_nome(membro) is None
    membro.edit.assert_not_awaited()


async def test_nome_vietato_senza_permessi_viene_detto(ambiente_nomi):
    membro = _membro("n1gg3r")
    membro.edit.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    assert "non riuscito" in await modulo_parole.controlla_nome(membro)
