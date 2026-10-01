"""
tests/test_config_rollback_bug6.py
=====================================
BUG-6: /config rollback riportava "✅" senza ripristinare niente per
reset e import (scriveva una setting spazzatura), non cambiava la lingua,
e trasformava in `null` una setting appena creata. Usa il database reale.
"""

import json

import pytest

from core.database import db

GUILD = 777000601


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    return clean_db


async def _ultima_voce():
    return (await db.get_config_history(GUILD, limit=1))[0]


@pytest.mark.asyncio
async def test_rollback_di_un_reset_ripristina_tutta_la_configurazione():
    await db.set_module_active_for_guild(GUILD, "tickets", True)
    await db.set_guild_setting(GUILD, "report_channel_id", 55)
    await db.set_guild_language(GUILD, "en")

    await db.reset_guild_config(GUILD, changed_by=1)
    assert await db.get_guild_setting(GUILD, "report_channel_id") is None

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is True

    completa = await db.get_full_config(GUILD)
    assert completa["modules"] == {"tickets": True}
    assert completa["settings"] == {"report_channel_id": 55}
    assert completa["language"] == "en"
    assert "guild_config" not in completa["settings"]


@pytest.mark.asyncio
async def test_rollback_di_un_import_ripristina_la_configurazione_precedente():
    await db.set_module_active_for_guild(GUILD, "tickets", True)
    await db.import_full_config(
        GUILD, modules={"poll": True}, settings={"x": 1}, language="en", changed_by=1
    )

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is True

    completa = await db.get_full_config(GUILD)
    assert completa["modules"] == {"tickets": True}
    assert completa["settings"] == {}
    assert completa["language"] == "it"


@pytest.mark.asyncio
async def test_rollback_della_lingua_cambia_la_colonna_language():
    await db.set_guild_language(GUILD, "en")

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is True

    assert await db.get_guild_language(GUILD) == "it"
    assert await db.get_guild_setting(GUILD, "language") is None  # niente setting spazzatura


@pytest.mark.asyncio
async def test_rollback_di_una_setting_nuova_la_rimuove_invece_di_metterla_a_null():
    await db.set_guild_setting(GUILD, "ticket_support_role_id", 99)

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is True

    chiavi = await db.pool.fetchval(
        "SELECT settings::text FROM guild_config WHERE guild_id = $1", GUILD
    )
    assert "ticket_support_role_id" not in json.loads(chiavi)


@pytest.mark.asyncio
async def test_rollback_non_ripristinabile_restituisce_false_non_successo():
    await db.ensure_guild_exists(GUILD)
    # Voce di reset con un valore "prima" che non è una configurazione.
    await db._record_config_change(GUILD, 1, "reset", "guild_config", "spazzatura", {})

    assert await db.rollback_config_change((await _ultima_voce()).id, rolled_back_by=1) is False
