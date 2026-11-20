"""
tests/test_lingua_iniziale.py
=============================
CFG-029 (#122): un server nuovo parte dalla lingua scelta su Discord; un server che c'è già non cambia lingua.
"""

from types import SimpleNamespace

import discord
import pytest

from core.i18n import lingua_iniziale_del_server


@pytest.mark.parametrize(
    "locale, atteso",
    [
        (discord.Locale.italian, "it"),
        (discord.Locale.american_english, "en"),
        (discord.Locale.british_english, "en"),
        (discord.Locale.german, "en"),  # senza testi propri si parte dall'inglese
        (discord.Locale.japanese, "en"),
        (None, "it"),
        ("non-una-lingua", "it"),
    ],
)
def test_la_lingua_di_partenza_segue_discord(locale, atteso):
    assert lingua_iniziale_del_server(SimpleNamespace(preferred_locale=locale)) == atteso
    assert lingua_iniziale_del_server(object()) == "it"


async def test_solo_la_riga_nuova_prende_la_lingua(clean_db, monkeypatch):
    import core.database as database_module

    db = database_module.db
    monkeypatch.setattr(db, "_pool", clean_db)
    await db.ensure_guild_exists(930, language="en")
    assert await db.get_guild_language(930) == "en"
    await db.ensure_guild_exists(930, language="it")  # rientro: la scelta resta
    assert await db.get_guild_language(930) == "en"
    await db.ensure_guild_exists(931)
    assert await db.get_guild_language(931) == "it"
