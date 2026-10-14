"""
tests/test_modules_updated.py
================================
M 10.13 (REVIEW §12, 1.2): l'evento `modules_updated` parte da OGNI
percorso che cambia lo stato dei moduli: wizard, import, reset, rollback
(oltre al salvataggio di `/admin setup attiva`, già coperto in test_setup_cog).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.utility.config_history as ch
import cogs.utility.setup as modulo_setup
import core.config_schema as config_schema_module
from cogs.utility.config_history import ConfigHistoryCog, ResetConfirmView, RollbackConfirmView
from cogs.utility.setup import SetupWizardView
from core.database import Database
from core.modules_updated_logic import moduli_cambiati
from core.premium import PremiumModule, PremiumRegistry
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

GUILD = 555000111


def test_moduli_cambiati_confronta_prima_e_dopo():
    prima = {"a": True, "b": False, "c": True}
    dopo = {"a": True, "b": True, "d": True, "c": False}
    assert sorted(moduli_cambiati(prima, dopo)) == [("b", True), ("c", False), ("d", True)]
    assert moduli_cambiati({"x": False}, {}) == []  # mancante = spento
    assert moduli_cambiati({}, {}) == []


@pytest.fixture
async def database(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD)
    monkeypatch.setattr(ch, "db", database)
    monkeypatch.setattr(modulo_setup, "db", database)
    monkeypatch.setattr(config_schema_module, "db", database)
    yield database
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD)
    await database.close()


def _interazione(user_id=42):
    i = fake_interaction(guild=fake_guild(guild_id=GUILD), user=fake_member(user_id=user_id))
    i.client = MagicMock()
    return i


def _eventi(interazione):
    return [c.args for c in interazione.client.dispatch.call_args_list if c.args[0] == "modules_updated"]


@pytest.mark.asyncio
async def test_reset_emette_per_ogni_modulo_che_si_spegne(database):
    await database.set_module_active_for_guild(GUILD, "mod_a", True)
    await database.set_module_active_for_guild(GUILD, "mod_b", False)
    vista = ResetConfirmView(GUILD, 42)
    interazione = _interazione()

    await vista.confirm.callback(interazione)

    assert _eventi(interazione) == [("modules_updated", GUILD, "mod_a", False, 42)]


@pytest.mark.asyncio
async def test_rollback_di_un_modulo_emette(database):
    await database.set_module_active_for_guild(GUILD, "mod_a", False, changed_by=1)
    await database.set_module_active_for_guild(GUILD, "mod_a", True, changed_by=1)
    voce = await database.pool.fetchval(
        "SELECT id FROM guild_config_history WHERE guild_id = $1 ORDER BY id DESC LIMIT 1", GUILD
    )
    vista = RollbackConfirmView(voce, 42)
    interazione = _interazione()

    await vista.confirm.callback(interazione)

    assert _eventi(interazione) == [("modules_updated", GUILD, "mod_a", False, 42)]


@pytest.mark.asyncio
async def test_rollback_fallito_non_emette(database):
    vista = RollbackConfirmView(999999, 42)
    interazione = _interazione()
    await vista.confirm.callback(interazione)
    assert _eventi(interazione) == []


@pytest.mark.asyncio
async def test_import_emette_solo_per_i_cambiati(database, monkeypatch):
    await database.set_module_active_for_guild(GUILD, "mod_a", True)
    await database.set_module_active_for_guild(GUILD, "mod_b", False)
    registro = PremiumRegistry()
    for nome in ("mod_a", "mod_b"):
        registro.register(PremiumModule(category="utility", name=nome, display_name=nome, description="d"))
    monkeypatch.setattr(ch, "registry", registro)
    dati = {"modules": {"mod_a": True, "mod_b": True}, "settings": {}, "language": "it"}
    file = MagicMock()
    file.size = 100
    file.read = AsyncMock(return_value=json.dumps(dati).encode())
    interazione = _interazione()
    cog = ConfigHistoryCog(MagicMock())

    await cog.import_config.callback(cog, interazione, file)

    assert _eventi(interazione) == [("modules_updated", GUILD, "mod_b", True, 42)]


@pytest.mark.asyncio
async def test_wizard_emette_per_i_moduli_cambiati(database, reset_premium_registry):
    from core.premium import registry

    a = PremiumModule(category="utility", name="wiz_a", display_name="A", description="A")
    b = PremiumModule(category="utility", name="wiz_b", display_name="B", description="B")
    registry.register(a)
    registry.register(b)  # imposta_modulo (D16) accetta solo moduli registrati
    await database.set_module_active_for_guild(GUILD, "wiz_a", True)
    await database.set_module_active_for_guild(GUILD, "wiz_b", False)
    vista = SetupWizardView(GUILD, [(a, True), (b, False)])
    vista.selected["wiz_b"] = True
    vista.step = 1  # ultimo passo
    interazione = _interazione()

    await vista.next_button.callback(interazione)

    assert _eventi(interazione) == [("modules_updated", GUILD, "wiz_b", True, 42)]
