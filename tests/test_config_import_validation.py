"""
tests/test_config_import_validation.py
=========================================
`/config import` deve validare lo schema PRIMA di scrivere e rifiutare i
dati sbagliati (PIANO_FIX R1, §4 Utility).
"""

import json

import pytest

from cogs.utility.config_history import ConfigHistoryCog, errore_schema_import
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction

VALIDO = {"modules": {"tickets": True}, "settings": {"report_channel_id": 5}, "language": "it"}


class TestErroreSchemaImport:
    def test_dati_validi_nessun_errore(self):
        assert errore_schema_import(VALIDO) is None

    @pytest.mark.parametrize(
        "dati",
        [
            {**VALIDO, "modules": []},
            {**VALIDO, "modules": {"tickets": "si"}},
            {**VALIDO, "modules": {"": True}},
            {**VALIDO, "settings": [1]},
            {**VALIDO, "language": "xx"},
            {**VALIDO, "language": 3},
            {"modules": {}, "settings": {}},
            [],
        ],
    )
    def test_dati_sbagliati_vengono_rifiutati(self, dati):
        assert errore_schema_import(dati) is not None


class _FakeFile:
    def __init__(self, contenuto: bytes, size: int | None = None):
        self._contenuto = contenuto
        self.size = len(contenuto) if size is None else size

    async def read(self):
        return self._contenuto


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()


async def _importa(contenuto: bytes, size=None):
    cog = ConfigHistoryCog(bot=None)
    interazione = fake_interaction(guild=fake_guild(guild_id=777000602))
    await cog.import_config.callback(cog, interazione, _FakeFile(contenuto, size))
    return interazione.response.send_message.call_args.args[0]


@pytest.mark.asyncio
async def test_import_con_schema_sbagliato_non_scrive_nulla():
    messaggio = await _importa(json.dumps({**VALIDO, "modules": {"tickets": "si"}}).encode())

    assert "✅" not in messaggio
    assert await db.get_full_config(777000602) == {"modules": {}, "settings": {}, "language": "it"}


@pytest.mark.asyncio
async def test_import_di_un_file_troppo_grande_viene_rifiutato():
    messaggio = await _importa(b"{}", size=10_000_000)

    assert "✅" not in messaggio


@pytest.mark.asyncio
async def test_import_valido_scrive():
    messaggio = await _importa(json.dumps(VALIDO).encode())

    assert "✅" in messaggio
    assert (await db.get_full_config(777000602))["modules"] == {"tickets": True}
