"""
tests/test_i18n_completo.py
===========================
NF-06 (#77): catalogo dei testi (locales/it.json, locales/en.json), lingua per server e per utente.
Senza il catalogo o con una chiave solo in una lingua il test fallisce.
"""

import json
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import i18n

SEGNAPOSTO = re.compile(r"\{(\w+)\}")


def _file(lingua):
    return json.loads((i18n.CARTELLA_LOCALES / f"{lingua}.json").read_text(encoding="utf-8"))


def test_le_due_lingue_hanno_le_stesse_chiavi():
    it, en = _file("it"), _file("en")
    assert sorted(set(it) ^ set(en)) == []


def test_stessi_segnaposto_e_nessun_testo_vuoto():
    it, en = _file("it"), _file("en")
    for chiave in it:
        assert it[chiave].strip() and en[chiave].strip(), chiave
        assert set(SEGNAPOSTO.findall(it[chiave])) == set(SEGNAPOSTO.findall(en[chiave])), chiave


def test_il_testo_inglese_non_e_una_copia_dell_italiano():
    it, en = _file("it"), _file("en")
    uguali = [k for k in it if it[k] == en[k] and len(it[k]) > 25]
    assert uguali == []


def test_t_riempie_i_segnaposto_e_non_solleva_mai():
    assert i18n.t("err_attesa", "en", secondi=4) == "Wait 4 seconds before running this command again."
    assert "{secondi}" in i18n.t("err_attesa", "it")  # segnaposto mancante: resta com'è
    assert i18n.t("chiave_che_non_esiste", "en") == "chiave_che_non_esiste"
    assert i18n.t("operation_cancelled", "fr") == _file("it")["operation_cancelled"]


def test_locale_di_discord_a_lingua_del_bot():
    assert i18n.da_locale_discord("it") == "it"
    assert i18n.da_locale_discord("en-US") == "en"
    assert i18n.da_locale_discord("en-GB") == "en"
    assert i18n.da_locale_discord("fr") is None


@pytest.mark.asyncio
async def test_la_lingua_personale_batte_quella_del_server_solo_se_privata(clean_db, monkeypatch):
    import core.database as database_module
    from core.repositories.user_language_repo import UserLanguageRepository

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(
        "core.repositories.user_language_repo.user_language_repo",
        UserLanguageRepository(pool_provider=lambda: clean_db),
    )
    await database_module.db.set_guild_language(900, "en")
    assert await i18n.lingua_risposta(900, 5) == "en"          # nessuna preferenza: il server
    assert await i18n.imposta_lingua_utente(5, "it") == "it"
    assert await i18n.lingua_risposta(900, 5) == "it"          # privata: vince l'utente
    assert await i18n.lingua_risposta(900, 5, pubblica=True) == "en"  # pubblica: il server
    assert await i18n.lingua_risposta(None, 5) == "it"         # DM: l'utente
    assert await i18n.imposta_lingua_utente(5, "server") is None
    assert await i18n.lingua_risposta(900, 5) == "en"
    with pytest.raises(ValueError):
        await i18n.imposta_lingua_utente(5, "fr")


@pytest.mark.asyncio
async def test_senza_database_si_risponde_in_italiano(monkeypatch):
    def rotto():
        raise RuntimeError("niente database")

    monkeypatch.setattr("core.repositories.user_language_repo.user_language_repo._pool_provider", rotto)
    assert await i18n.lingua_risposta(1, 2) == "it"


@pytest.mark.asyncio
async def test_il_gestore_errori_risponde_nella_lingua_dell_utente(clean_db, monkeypatch):
    import core.database as database_module
    from discord import app_commands

    from core.premium import handle_app_command_error
    from core.repositories.user_language_repo import UserLanguageRepository

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(
        "core.repositories.user_language_repo.user_language_repo",
        UserLanguageRepository(pool_provider=lambda: clean_db),
    )
    await i18n.imposta_lingua_utente(77, "en")
    interazione = MagicMock()
    interazione.user.id = 77
    interazione.guild.id = 901
    interazione.response.is_done = MagicMock(return_value=False)
    interazione.response.send_message = AsyncMock()
    await handle_app_command_error(interazione, app_commands.MissingPermissions(["manage_guild"]))
    testo = interazione.response.send_message.call_args.args[0]
    assert testo == _file("en")["err_permessi_utente"]


@pytest.mark.asyncio
async def test_utility_lingua_mostra_imposta_e_toglie(clean_db, monkeypatch):
    import discord
    from discord import app_commands
    from discord.ext import commands

    import core.database as database_module
    from core.repositories.user_language_repo import UserLanguageRepository

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(
        "core.repositories.user_language_repo.user_language_repo",
        UserLanguageRepository(pool_provider=lambda: clean_db),
    )
    import cogs.utility.lingua as modulo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await modulo.setup(bot)
    cog = bot.get_cog("LinguaCog")
    try:
        async def esegui(scelta):
            i = MagicMock()
            i.user.id = 31
            i.guild.id = 902
            i.response.send_message = AsyncMock()
            await cog.lingua.callback(cog, i, None if scelta is None else app_commands.Choice(name="x", value=scelta))
            return i.response.send_message.call_args.args[0]

        assert "server" in (await esegui(None)).lower()
        assert "english" in (await esegui("en")).lower() or "personal" in (await esegui("en")).lower()
        assert await i18n.lingua_utente(31) == "en"
        assert "Your language" in await esegui(None)
        await esegui("server")
        assert await i18n.lingua_utente(31) is None
    finally:
        await bot.close()
