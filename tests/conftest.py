"""
tests/conftest.py
====================
Configurazione condivisa dei test. Due responsabilità:

1. Imposta variabili d'ambiente FITTIZIE prima che qualsiasi modulo
   del progetto venga importato. core/config.py valida tutto
   all'import (è la sua caratteristica principale, vedi quel file)
   quindi nei test serve popolare comunque tutte le variabili
   obbligatorie — con valori finti per Discord (non serve un vero
   bot online per testare la logica o il database), ma con un
   DATABASE_URL VERO che punta al database Postgres locale di test
   installato nel container.

2. Fornisce una fixture `db_pool` che apre/chiude un pool reale
   verso quel database per i test che ne hanno bisogno, e una
   fixture `clean_db` che pulisce le tabelle tra un test e l'altro
   così i test non si influenzano a vicenda.
"""

import os

# Deve avvenire PRIMA di ogni import da "core.*": core/config.py
# valida le variabili al momento dell'import del modulo stesso.
os.environ.setdefault("YOKAI_BOT_TOKEN", "test-token-fittizio")
os.environ.setdefault("YOKAI_CREATOR_TOKEN", "test-token-fittizio")
for i in range(1, 6):
    os.environ.setdefault(f"MUSIC_TOKEN_{i}", "test-token-fittizio")
os.environ.setdefault("NSFW_TOKEN", "test-token-fittizio")
os.environ.setdefault("OWNER_ID", "123456789")
os.environ.setdefault("MAIN_GUILD_ID", "987654321")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:testpass@127.0.0.1:5432/iyokai_test",
)
os.environ.setdefault("ENVIRONMENT", "development")

import asyncpg
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def db_pool():
    """
    Pool reale, aperto e chiuso per ogni test che lo richiede.
    Scope "function" (default): ogni test parte con un pool pulito,
    niente stato condiviso accidentale tra test diversi.
    """
    pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"], min_size=1, max_size=3
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def clean_db(db_pool):
    """
    Applica le migration e SVUOTA le tabelle prima di ogni test.
    Import locale (non in cima al file) per essere sicuri che le
    variabili d'ambiente sopra siano già impostate quando i moduli
    core.* vengono importati.
    """
    from core.database import db as db_singleton
    from core.scheduler import run_migrations as scheduler_migrations
    from core.repositories.moderation_repo import (
        run_migrations as moderation_migrations,
    )
    from core.repositories.automod_repo import (
        run_migrations as automod_migrations,
    )
    from core.repositories.ticket_repo import (
        run_migrations as ticket_migrations,
    )
    from core.repositories.voice_temp_repo import (
        run_migrations as voice_temp_migrations,
    )

    # Riusiamo lo stesso pool del test per le migration, invece di
    # farne aprire uno secondo al singleton: gli passiamo il pool
    # direttamente.
    await db_singleton_run_migrations_with_pool(db_pool)
    await scheduler_migrations(db_pool)
    await moderation_migrations(db_pool)
    await automod_migrations(db_pool)
    await ticket_migrations(db_pool)
    await voice_temp_migrations(db_pool)

    # Pulizia: TRUNCATE è più veloce di DELETE e resetta i contatori
    # SERIAL, utile perché alcuni test controllano id progressivi.
    tables = [
        "scheduled_actions",
        "moderation_cases",
        "moderation_notes",
        "moderation_case_counters",
        "automod_config",
        "automod_last_synced",
        "tickets",
        "ticket_counters",
        "voice_temp_config",
        "voice_temp_channels",
        "guild_config",
        "premium_whitelist",
        "premium_module_flags",
    ]
    async with db_pool.acquire() as conn:
        for table in tables:
            exists = await conn.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", f"public.{table}"
            )
            if exists:
                await conn.execute(f"TRUNCATE TABLE {table} CASCADE")

    yield db_pool


async def db_singleton_run_migrations_with_pool(pool):
    """
    core.database.Database.run_migrations() usa self.pool, che
    richiede connect() già chiamato sul singleton. Nei test non
    vogliamo aprire un secondo pool globale: eseguiamo lo stesso SQL
    delle migration passando il pool di test direttamente.
    Tenuto in sync manualmente con core/database.py.run_migrations().
    """
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id        BIGINT PRIMARY KEY,
            modules         JSONB NOT NULL DEFAULT '{}'::jsonb,
            prefix          TEXT,
            language        TEXT NOT NULL DEFAULT 'it',
            setup_completed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS premium_whitelist (
            guild_id  BIGINT PRIMARY KEY,
            added_by  BIGINT NOT NULL,
            reason    TEXT,
            added_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS premium_module_flags (
            module_name TEXT PRIMARY KEY,
            is_active   BOOLEAN NOT NULL DEFAULT FALSE,
            updated_by  BIGINT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
