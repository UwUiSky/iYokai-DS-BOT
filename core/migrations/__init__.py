"""
core/migrations/__init__.py
===============================
Migrazioni del database, punto di ingresso unico per produzione
(core/database.py) e test (tests/conftest.py). Prima la base idempotente
(tabelle di configurazione e le run_migrations() dei repository), poi i
file numerati "NNNN_descrizione.sql"/".py" di questa cartella, ognuno
applicato una volta sola nella propria transazione. Tutto gira su una
sola connessione che tiene un pg_advisory_lock, così due processi che
partono insieme si mettono in fila. Una migrazione già applicata non si
modifica mai: se ne aggiunge una nuova con un numero più alto.
Funzioni coperte: PIANO_FIX.md "DB — Migrazioni versionate (DB-1, #25)"
"""

from __future__ import annotations

import importlib.util
import logging
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import asyncpg

logger = logging.getLogger("iyokai.migrations")

# Lock advisory Postgres: basta che sia un numero fisso, sempre lo
# stesso tra un avvio e l'altro di questo progetto — non ha nessun
# significato oltre a "questo processo sta applicando le migrazioni
# numerate di iYokai, aspetta il tuo turno". Scelto a caso, non è un
# anno/data/versione da tenere aggiornato.
ADVISORY_LOCK_ID = 822025001

MIGRATIONS_DIR = Path(__file__).parent

VERSION_PATTERN = re.compile(r"^(\d{4})_.+\.(sql|py)$")

# asyncpg applica a ogni query il command_timeout del pool (30 secondi in
# produzione): troppo poco per aspettare il lock o per una migrazione su
# una tabella grande. Un giorno vale "nessun limite". Una migrazione .py
# con query lunghe passa questo valore come `timeout=` alle sue query.
TIMEOUT_MIGRAZIONE = 24 * 60 * 60


class MigrationError(Exception):
    """Cartella delle migrazioni non valida: nome fuori formato o numero doppio."""


@dataclass(frozen=True)
class MigrationFile:
    version: int
    name: str
    path: Path


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[MigrationFile]:
    """
    Elenca le migrazioni numerate in ordine di versione. Un file
    "NNNN_descrizione.sql" viene eseguito come SQL grezzo; un file
    "NNNN_descrizione.py" deve esporre `async def up(conn)`.
    Solleva MigrationError se un file .sql/.py (tranne __init__.py) non
    segue il formato o se due file hanno lo stesso numero: saltarli in
    silenzio lascerebbe lo schema a metà senza che nessuno se ne accorga.
    """
    if not migrations_dir.is_dir():
        return []

    per_versione: dict[int, MigrationFile] = {}
    for path in sorted(migrations_dir.iterdir()):
        if path.name == "__init__.py" or path.suffix not in (".sql", ".py"):
            continue
        corrispondenza = VERSION_PATTERN.match(path.name)
        if corrispondenza is None:
            raise MigrationError(
                f"Migrazione con nome non valido: '{path.name}'. "
                "Formato atteso: NNNN_descrizione.sql oppure .py (4 cifre)."
            )
        version = int(corrispondenza.group(1))
        if version in per_versione:
            raise MigrationError(
                f"Due migrazioni con lo stesso numero {version:04d}: "
                f"'{per_versione[version].path.name}' e '{path.name}'."
            )
        per_versione[version] = MigrationFile(version=version, name=path.stem, path=path)

    return [per_versione[version] for version in sorted(per_versione)]


@asynccontextmanager
async def _connessione_con_lock(pool: asyncpg.Pool):
    """
    Una connessione del pool con il lock advisory preso (i lock advisory
    sono legati alla connessione, non al pool). Chi arriva secondo
    aspetta qui il proprio turno, senza limite di tempo.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT pg_advisory_lock($1)", ADVISORY_LOCK_ID, timeout=TIMEOUT_MIGRAZIONE
        )
        try:
            yield conn
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_ID)


async def ensure_schema_migrations_table(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INT PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


async def _applica_una_migrazione(conn: asyncpg.Connection, migrazione: MigrationFile) -> None:
    if migrazione.path.suffix == ".sql":
        sql = migrazione.path.read_text(encoding="utf-8")
        await conn.execute(sql, timeout=TIMEOUT_MIGRAZIONE)
    else:
        spec = importlib.util.spec_from_file_location(migrazione.name, migrazione.path)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        await modulo.up(conn)


async def _applica_numerate(conn: asyncpg.Connection, migrazioni: list[MigrationFile]) -> list[int]:
    """Da chiamare con il lock già preso su `conn`."""
    await ensure_schema_migrations_table(conn)
    righe = await conn.fetch("SELECT version FROM schema_migrations")
    gia_applicate = {r["version"] for r in righe}

    applicate: list[int] = []
    for migrazione in migrazioni:
        if migrazione.version in gia_applicate:
            continue
        async with conn.transaction():
            await _applica_una_migrazione(conn, migrazione)
            await conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
                migrazione.version,
                migrazione.name,
            )
        applicate.append(migrazione.version)
        logger.info("Migrazione applicata: %s", migrazione.name)
    return applicate


async def apply_numbered_migrations(
    pool: asyncpg.Pool, migrations_dir: Path = MIGRATIONS_DIR
) -> list[int]:
    """
    Applica in ordine le migrazioni numerate non ancora registrate in
    schema_migrations. Ciascuna gira nella sua transazione: se una
    fallisce, SOLO quella fa rollback (le precedenti restano applicate).
    Restituisce le versioni applicate in QUESTA chiamata (lista vuota
    se non c'era nulla da fare, incluso il caso "un altro processo le
    ha già applicate mentre aspettavamo il lock").
    """
    migrazioni = discover_migrations(migrations_dir)
    if not migrazioni:
        return []
    async with _connessione_con_lock(pool) as conn:
        return await _applica_numerate(conn, migrazioni)


async def run_core_config_tables(pool: asyncpg.Pool) -> None:
    """
    Le tabelle di base di configurazione/premium — prima vivevano
    inline dentro core.database.Database.run_migrations(). Spostate
    qui perché anche tests/conftest.py deve poterle creare senza
    duplicare l'SQL a mano (era il problema di fondo di DB-1: due
    copie della stessa cosa, una in produzione e una nei test, tenute
    "in sync manualmente").
    """
    await pool.execute(
        """
        -- Configurazione per-server: un JSONB per i moduli
        -- attivi, così l'attivazione/disattivazione di un
        -- modulo non richiede una ALTER TABLE ogni volta che
        -- se ne aggiunge uno nuovo.
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id        BIGINT PRIMARY KEY,
            modules         JSONB NOT NULL DEFAULT '{}'::jsonb,
            settings        JSONB NOT NULL DEFAULT '{}'::jsonb,
            prefix          TEXT,
            language        TEXT NOT NULL DEFAULT 'it',
            setup_completed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Se la tabella esisteva già da una versione precedente
        -- (senza la colonna settings), la aggiunge senza
        -- toccare i dati esistenti. IF NOT EXISTS la rende
        -- sicura da rieseguire ad ogni avvio.
        ALTER TABLE guild_config
            ADD COLUMN IF NOT EXISTS settings JSONB NOT NULL DEFAULT '{}'::jsonb;

        -- Whitelist Premium: server ID aggiunti a mano
        -- dall'owner del bot. Vedi core/premium.py.
        CREATE TABLE IF NOT EXISTS premium_whitelist (
            guild_id  BIGINT PRIMARY KEY,
            added_by  BIGINT NOT NULL,
            reason    TEXT,
            added_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Stato delle flag premium per modulo. Persistito qui
        -- così sopravvive a un riavvio del bot (il registry
        -- in memoria, core/premium.py, viene ricaricato da
        -- questa tabella all'avvio).
        CREATE TABLE IF NOT EXISTS premium_module_flags (
            module_name TEXT PRIMARY KEY,
            is_active   BOOLEAN NOT NULL DEFAULT FALSE,
            updated_by  BIGINT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Config Diff & Rollback (BACKLOG.md §11, estensione
        -- di SPEC.md §2.7): ogni scrittura su modules/settings
        -- passa da set_module_active_for_guild()/
        -- set_guild_setting() in core/database.py, che registrano
        -- qui il valore precedente e quello nuovo PRIMA di
        -- scrivere. change_type distingue "module" da
        -- "setting" (stessa tabella per entrambi, non due
        -- tabelle quasi identiche). old_value/new_value sono
        -- JSON-encoded (non colonne tipizzate: i valori
        -- possono essere bool, int, str a seconda della
        -- chiave) — stesso approccio già in uso per
        -- guild_config.settings.
        CREATE TABLE IF NOT EXISTS guild_config_history (
            id          SERIAL PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            changed_by  BIGINT,
            change_type TEXT NOT NULL,
            key_name    TEXT NOT NULL,
            old_value   TEXT,
            new_value   TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_guild_config_history_guild
            ON guild_config_history (guild_id, created_at DESC);

        -- Log persistente dei cambi premium (SPEC.md §17.10,
        -- pannello interattivo) — append-only, distinta da
        -- premium_module_flags (che tiene solo lo stato PIÙ
        -- RECENTE): qui ogni singolo cambiamento resta nello
        -- storico, anche dopo che un cambio successivo lo ha
        -- superato.
        CREATE TABLE IF NOT EXISTS premium_toggle_history (
            id           SERIAL PRIMARY KEY,
            module_name  TEXT NOT NULL,
            new_value    BOOLEAN NOT NULL,
            changed_by   BIGINT NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_premium_toggle_history_module
            ON premium_toggle_history (module_name, created_at DESC);
        """
    )


async def run_all_repo_migrations(pool: asyncpg.Pool) -> None:
    """
    Le funzioni run_migrations(pool) di ogni repository, in sequenza
    — stessa lista che prima viveva duplicata dentro
    core.database.Database.run_migrations() E dentro
    tests/conftest.py. Un modulo nuovo aggiunge qui la propria riga
    (una sola volta, non più due).
    """
    from core.scheduler import run_migrations as scheduler_migrations
    await scheduler_migrations(pool)

    from core.repositories.moderation_repo import run_migrations as moderation_migrations
    await moderation_migrations(pool)

    from core.repositories.automod_repo import run_migrations as automod_migrations
    await automod_migrations(pool)

    from core.repositories.ticket_repo import run_migrations as ticket_migrations
    await ticket_migrations(pool)

    from core.repositories.voice_temp_repo import run_migrations as voice_temp_migrations
    await voice_temp_migrations(pool)

    from core.repositories.leveling_repo import run_migrations as leveling_migrations
    await leveling_migrations(pool)

    from core.repositories.spam_trap_repo import run_migrations as spam_trap_migrations
    await spam_trap_migrations(pool)

    from core.repositories.verify_repo import run_migrations as verify_migrations
    await verify_migrations(pool)

    from core.repositories.role_menu_repo import run_migrations as role_menu_migrations
    await role_menu_migrations(pool)

    from core.repositories.greetings_repo import run_migrations as greetings_migrations
    await greetings_migrations(pool)

    from core.repositories.escalation_repo import run_migrations as escalation_migrations
    await escalation_migrations(pool)

    from core.repositories.event_log_repo import run_migrations as event_log_migrations
    await event_log_migrations(pool)

    from core.repositories.sticky_message_repo import run_migrations as sticky_message_migrations
    await sticky_message_migrations(pool)

    from core.repositories.suggestion_repo import run_migrations as suggestion_migrations
    await suggestion_migrations(pool)

    from core.repositories.custom_command_request_repo import (
        run_migrations as custom_command_request_migrations,
    )
    await custom_command_request_migrations(pool)

    from core.repositories.blacklist_repo import run_migrations as blacklist_migrations
    await blacklist_migrations(pool)

    from core.repositories.eval_shell_log_repo import run_migrations as eval_shell_log_migrations
    await eval_shell_log_migrations(pool)

    from core.repositories.feed_subscription_repo import (
        run_migrations as feed_subscription_migrations,
    )
    await feed_subscription_migrations(pool)

    from core.repositories.custom_webhook_repo import run_migrations as custom_webhook_migrations
    await custom_webhook_migrations(pool)

    from core.repositories.music_session_repo import run_migrations as music_session_migrations
    await music_session_migrations(pool)

    from core.repositories.twitch_subscription_repo import (
        run_migrations as twitch_subscription_migrations,
    )
    await twitch_subscription_migrations(pool)

    from core.repositories.youtube_subscription_repo import (
        run_migrations as youtube_subscription_migrations,
    )
    await youtube_subscription_migrations(pool)

    from core.repositories.main_radio_repo import run_migrations as main_radio_migrations
    await main_radio_migrations(pool)

    from core.repositories.backup_repo import run_migrations as backup_migrations
    await backup_migrations(pool)

    from core.repositories.backup_mirror_repo import run_migrations as backup_mirror_migrations
    await backup_mirror_migrations(pool)

    from core.repositories.backup_user_snapshot_repo import (
        run_migrations as backup_user_snapshot_migrations,
    )
    await backup_user_snapshot_migrations(pool)

    from core.repositories.restore_oauth_repo import run_migrations as restore_oauth_migrations
    await restore_oauth_migrations(pool)

    from core.repositories.level_reward_repo import run_migrations as level_reward_migrations
    await level_reward_migrations(pool)

    from core.repositories.monthly_winners_repo import (
        run_migrations as monthly_winners_migrations,
    )
    await monthly_winners_migrations(pool)

    from core.repositories.clan_leaderboard_config_repo import (
        run_migrations as clan_leaderboard_config_migrations,
    )
    await clan_leaderboard_config_migrations(pool)

    from core.repositories.module_subscription_repo import (
        run_migrations as module_subscription_migrations,
    )
    await module_subscription_migrations(pool)

    from core.repositories.shop_repo import run_migrations as shop_migrations
    await shop_migrations(pool)

    from core.repositories.giveaway_repo import run_migrations as giveaway_migrations
    await giveaway_migrations(pool)

    from core.repositories.guild_clan_repo import run_migrations as guild_clan_migrations
    await guild_clan_migrations(pool)

    from core.repositories.clan_voice_activity_repo import (
        run_migrations as clan_voice_activity_migrations,
    )
    await clan_voice_activity_migrations(pool)

    from core.repositories.guild_chest_repo import run_migrations as guild_chest_migrations
    await guild_chest_migrations(pool)

    from core.repositories.guild_premium_repo import run_migrations as guild_premium_migrations
    await guild_premium_migrations(pool)

    from core.repositories.automod_advanced_repo import (
        run_migrations as automod_advanced_migrations,
    )
    await automod_advanced_migrations(pool)

    from core.repositories.security_repo import run_migrations as security_migrations
    await security_migrations(pool)

    from core.repositories.global_ban_repo import run_migrations as global_ban_migrations
    await global_ban_migrations(pool)

    # I repository dei singoli moduli aggiungono qui la propria riga
    # mano a mano che vengono scritti — vedi core/repositories/ e la
    # nota in fondo a core/database.py.


async def run_all_migrations(pool: asyncpg.Pool) -> None:
    """
    Punto di ingresso unico: tabelle di base, poi tutte le run_
    migrations() di repository (idempotenti, girano sempre), poi le
    migrazioni numerate non ancora applicate. Tutto sulla connessione
    che tiene il lock: anche i CREATE TABLE IF NOT EXISTS della base, se
    lanciati da due processi insieme su un database vuoto, falliscono.
    Le funzioni di base ricevono la connessione al posto del pool (usano
    solo `.execute`, che hanno entrambi).
    """
    migrazioni = discover_migrations()  # prima di tutto: un nome sbagliato ferma l'avvio
    async with _connessione_con_lock(pool) as conn:
        await run_core_config_tables(conn)
        await run_all_repo_migrations(conn)
        await _applica_numerate(conn, migrazioni)
