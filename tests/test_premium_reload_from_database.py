"""
tests/test_premium_reload_from_database.py
===============================================
Test di core.premium.reload_premium_flags_from_database (SPEC.md
§3.3): la ricarica delle flag premium dal DB nel registry in memoria
all'avvio del bot. Debito reale trovato durante il lavoro su §3
(nitro boost + abbonamenti): la tabella `premium_module_flags` viene
scritta da `_apply_premium_toggle` (cogs/utility/owner_premium.py)
ma nessun consumatore la rileggeva mai — lo stato premium sopravviveva
in DB ma non veniva mai riapplicato al registry dopo un riavvio.
"""

import pytest

from core.database import Database
from core.premium import PremiumModule, reload_premium_flags_from_database, registry


@pytest.fixture
async def database():
    db = Database()
    await db.connect()
    await db.run_migrations()
    await db.pool.execute(
        "DELETE FROM premium_module_flags WHERE module_name LIKE 'test_reload_%'"
    )

    from core.database import db as real_db_singleton
    original_pool = real_db_singleton._pool
    real_db_singleton._pool = db.pool

    yield db

    real_db_singleton._pool = original_pool
    await db.pool.execute(
        "DELETE FROM premium_module_flags WHERE module_name LIKE 'test_reload_%'"
    )
    await db.close()


@pytest.mark.asyncio
async def test_ricarica_applica_lo_stato_attivo_dal_db(database):
    registry.register(
        PremiumModule(
            category="utility",
            name="test_reload_attivo", display_name="Modulo Test", description="x"
        )
    )
    await database.pool.execute(
        "INSERT INTO premium_module_flags (module_name, is_active, updated_by) "
        "VALUES ('test_reload_attivo', TRUE, 1)"
    )

    await reload_premium_flags_from_database()

    assert registry.get("test_reload_attivo").is_premium_active is True


@pytest.mark.asyncio
async def test_ricarica_ignora_modulo_non_registrato_senza_sollevare(database):
    await database.pool.execute(
        "INSERT INTO premium_module_flags (module_name, is_active, updated_by) "
        "VALUES ('test_reload_mai_registrato', TRUE, 1)"
    )

    await reload_premium_flags_from_database()  # non deve sollevare


@pytest.mark.asyncio
async def test_ricarica_ignora_modulo_diventato_sempre_gratuito(database):
    registry.register(
        PremiumModule(
            category="utility",
            name="test_reload_gratuito",
            display_name="Modulo Test",
            description="x",
            premium_capable=False,
        )
    )
    await database.pool.execute(
        "INSERT INTO premium_module_flags (module_name, is_active, updated_by) "
        "VALUES ('test_reload_gratuito', TRUE, 1)"
    )

    await reload_premium_flags_from_database()  # non deve sollevare
