"""
tests/test_config_schema.py
===========================
Il punto unico delle impostazioni (D16, SPEC §24.3): stesso controllo e
stesso storico per comandi e pannello web.
"""

from unittest.mock import MagicMock

import pytest

import core.database as database_module
from core.config_schema import (
    ImpostazioneNonValida,
    imposta_lingua_server,
    imposta_modulo,
    valida_lingua,
    valida_modulo,
)
from core.database import db
from core.premium import PremiumModule, registry

GUILD = 9100


@pytest.fixture
def pool(monkeypatch, clean_db, reset_premium_registry):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    registry.register(PremiumModule("prova_pannello", "Prova", "Modulo di prova", category="utility"))
    return clean_db


def test_valida_modulo_rifiuta_nomi_sconosciuti(reset_premium_registry):
    with pytest.raises(ImpostazioneNonValida):
        valida_modulo("non_esiste")


def test_valida_lingua():
    assert valida_lingua("en") == "en"
    with pytest.raises(ImpostazioneNonValida):
        valida_lingua("xx")


@pytest.mark.asyncio
async def test_imposta_modulo_scrive_storico_ed_evento(pool):
    client = MagicMock()
    assert await imposta_modulo(client, GUILD, "prova_pannello", True, 77) is True
    assert await db.is_module_active_for_guild(GUILD, "prova_pannello") is True
    client.dispatch.assert_called_once_with("modules_updated", GUILD, "prova_pannello", True, 77)
    storico = await db.get_config_history(GUILD)
    assert storico[0].key_name == "prova_pannello" and storico[0].changed_by == 77


@pytest.mark.asyncio
async def test_imposta_modulo_senza_cambio_non_scrive(pool):
    client = MagicMock()
    assert await imposta_modulo(client, GUILD, "prova_pannello", False, 77) is False
    client.dispatch.assert_not_called()
    assert await db.get_config_history(GUILD) == []


@pytest.mark.asyncio
async def test_imposta_modulo_sconosciuto_non_tocca_il_database(pool):
    with pytest.raises(ImpostazioneNonValida):
        await imposta_modulo(None, GUILD, "inventato", True, 77)
    assert await db.get_config_history(GUILD) == []


@pytest.mark.asyncio
async def test_imposta_lingua_server(pool):
    await imposta_lingua_server(GUILD, "en", 5)
    assert await db.get_guild_language(GUILD) == "en"
    with pytest.raises(ImpostazioneNonValida):
        await imposta_lingua_server(GUILD, "de", 5)
    assert await db.get_guild_language(GUILD) == "en"
