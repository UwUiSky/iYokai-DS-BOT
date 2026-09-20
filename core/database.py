"""
core/database.py
==================
Layer UNICO di accesso al database. Regola ferrea del progetto:

    NESSUN cog scrive mai SQL direttamente.
    Ogni query passa da un metodo di questa classe (o di una classe
    "repository" simile, quando il file crescerà — vedi nota in fondo).

Perché questa regola è importante qui in particolare: è la stessa
ragione per cui, nella discussione di progetto, il passaggio da
SQLite a PostgreSQL era rischioso SOLO se le query erano sparse nei
cog. Con questo layer in mezzo, il giorno in cui cambierà qualcosa
nello schema del database (es. partizionamento di una tabella),
si tocca questo file, non quaranta cog diversi.

Connection pool
-----------------
asyncpg gestisce da solo un pool di connessioni riutilizzabili.
Non è mai necessario aprire/chiudere una connessione manualmente nei
cog: si prende una connessione dal pool solo per la durata della
singola query, e torna disponibile subito dopo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.bounded_cache import BoundedCache
from core.config import config


@dataclass(frozen=True)
class ConfigHistoryEntry:
    id: int
    guild_id: int
    changed_by: int | None
    change_type: str  # "module" | "setting"
    key_name: str
    old_value: object  # già deserializzato (bool, int, str, None...)
    new_value: object
    created_at: datetime


class Database:
    """
    Wrapper attorno al pool di connessioni.
    Un'unica istanza condivisa da tutto il bot (vedi `db` in fondo).
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        # Cache della colonna "modules" per server (BACKLOG.md §1,
        # priorità accettata dopo l'analisi delle proposte esterne):
        # ogni cog che condivide on_message/on_raw_reaction_add
        # (leveling, spam_trap, verify, role_menus, greetings — e in
        # crescita) chiamava is_module_active_for_guild() con una
        # query separata ad ogni singolo evento. Un dizionario intero
        # per chiave (non una entry per singolo modulo) così più cog
        # che controllano moduli diversi per LO STESSO server
        # condividono la stessa riga già in cache, invece di avere
        # una entry ciascuno.
        self._modules_cache: BoundedCache[int, dict] = BoundedCache(max_size=10_000)

    async def connect(self) -> None:
        """
        Apre il pool. Va chiamato UNA volta, all'avvio del bot
        (vedi main.py). Se viene chiamato due volte per errore,
        solleva un'eccezione chiara invece di creare due pool
        silenziosamente.
        """
        if self._pool is not None:
            raise RuntimeError("Il pool del database è già aperto.")

        self._pool = await asyncpg.create_pool(
            dsn=config.DATABASE_URL,
            min_size=config.DB_POOL_MIN,
            max_size=config.DB_POOL_MAX,
            # Timeout di comando: se una query impiega più di 30s,
            # meglio fallire rumorosamente che bloccare il bot.
            command_timeout=30,
        )

    async def close(self) -> None:
        """Chiude il pool in modo pulito. Va chiamato allo spegnimento."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        """
        Accesso diretto al pool per query non ancora "wrappate" in
        un metodo dedicato. Va usato con parsimonia: se un cog usa
        `db.pool.fetch(...)` direttamente più di una volta per la
        stessa cosa, quella query merita il suo metodo qui sotto.
        """
        if self._pool is None:
            raise RuntimeError(
                "Il pool del database non è ancora stato aperto. "
                "connect() va chiamato prima di qualsiasi query."
            )
        return self._pool

    # ================================================================
    # SCHEMA — creazione tabelle
    # ================================================================
    # In questa fase iniziale le tabelle vengono create qui, con
    # CREATE TABLE IF NOT EXISTS. Quando il progetto crescerà,
    # questo verrà sostituito da un vero sistema di migration
    # (es. Alembic), ma per partire subito questo approccio è
    # sufficiente e non introduce dipendenze extra.
    async def run_migrations(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
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
                -- set_guild_setting() più sotto, che registrano qui
                -- il valore precedente e quello nuovo PRIMA di
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
                """
            )

        # Migrazioni degli altri sottosistemi core. Ognuno espone il
        # proprio run_migrations(pool) e viene chiamato qui in
        # sequenza — così ogni modulo resta responsabile del proprio
        # schema, ma c'è un solo punto che li invoca tutti in ordine
        # all'avvio del bot.
        from core.scheduler import run_migrations as scheduler_migrations
        await scheduler_migrations(self.pool)

        from core.repositories.moderation_repo import (
            run_migrations as moderation_migrations,
        )
        await moderation_migrations(self.pool)

        from core.repositories.automod_repo import (
            run_migrations as automod_migrations,
        )
        await automod_migrations(self.pool)

        from core.repositories.ticket_repo import (
            run_migrations as ticket_migrations,
        )
        await ticket_migrations(self.pool)

        from core.repositories.voice_temp_repo import (
            run_migrations as voice_temp_migrations,
        )
        await voice_temp_migrations(self.pool)

        from core.repositories.leveling_repo import (
            run_migrations as leveling_migrations,
        )
        await leveling_migrations(self.pool)

        from core.repositories.spam_trap_repo import (
            run_migrations as spam_trap_migrations,
        )
        await spam_trap_migrations(self.pool)

        from core.repositories.verify_repo import (
            run_migrations as verify_migrations,
        )
        await verify_migrations(self.pool)

        from core.repositories.role_menu_repo import (
            run_migrations as role_menu_migrations,
        )
        await role_menu_migrations(self.pool)

        from core.repositories.greetings_repo import (
            run_migrations as greetings_migrations,
        )
        await greetings_migrations(self.pool)

        from core.repositories.escalation_repo import (
            run_migrations as escalation_migrations,
        )
        await escalation_migrations(self.pool)

        from core.repositories.event_log_repo import (
            run_migrations as event_log_migrations,
        )
        await event_log_migrations(self.pool)

        from core.repositories.sticky_message_repo import (
            run_migrations as sticky_message_migrations,
        )
        await sticky_message_migrations(self.pool)

        from core.repositories.suggestion_repo import (
            run_migrations as suggestion_migrations,
        )
        await suggestion_migrations(self.pool)

        from core.repositories.custom_command_request_repo import (
            run_migrations as custom_command_request_migrations,
        )
        await custom_command_request_migrations(self.pool)

        # I repository dei singoli moduli (moderation, leveling, ...)
        # aggiungono qui la propria riga mano a mano che vengono
        # scritti. Vedi core/repositories/ e la nota in fondo a
        # questo file.

    # ================================================================
    # Guild config — metodi di base
    # ================================================================
    async def ensure_guild_exists(self, guild_id: int) -> None:
        """
        Crea la riga di configurazione per un server se non esiste
        già. Chiamato da on_guild_join. ON CONFLICT DO NOTHING evita
        una race condition se per qualche motivo viene chiamato due
        volte in rapida successione.
        """
        await self.pool.execute(
            """
            INSERT INTO guild_config (guild_id)
            VALUES ($1)
            ON CONFLICT (guild_id) DO NOTHING
            """,
            guild_id,
        )

    async def is_module_active_for_guild(
        self, guild_id: int, module_name: str
    ) -> bool:
        """
        Controlla se un server ha attivato un certo modulo dal
        pannello di setup. Usato dal check runtime dei cog per
        decidere se rispondere o ignorare un comando o un evento
        (on_message, on_raw_reaction_add, ecc.).

        Passa dalla cache dei moduli per server (invalidata
        esplicitamente da set_module_active_for_guild, non a
        scadenza temporale — non c'è modo che diventi stantia senza
        che qualcuno l'abbia già aggiornata).
        """
        modules = self._modules_cache.get(guild_id)
        if modules is None:
            row = await self.pool.fetchrow(
                "SELECT modules FROM guild_config WHERE guild_id = $1",
                guild_id,
            )
            # asyncpg non ha un codec JSONB registrato in questo
            # progetto (vedi get_guild_setting più sotto, stesso
            # pattern): il campo torna come stringa JSON grezza, va
            # deserializzato esplicitamente.
            modules = json.loads(row["modules"]) if row is not None else {}
            self._modules_cache.set(guild_id, modules)

        return bool(modules.get(module_name, False))

    async def set_module_active_for_guild(
        self, guild_id: int, module_name: str, active: bool, changed_by: int | None = None
    ) -> None:
        """
        Attiva/disattiva un modulo per un server specifico. Crea la
        riga di config se non esiste ancora (server nuovo che non ha
        ancora ricevuto on_guild_join, capita nei test).

        changed_by è opzionale (default None) per restare compatibile
        con i chiamanti esistenti che non lo passano ancora — ogni
        scrittura viene comunque registrata nello storico
        (guild_config_history, BACKLOG.md §11 Config Diff & Rollback),
        anche con changed_by NULL se l'autore non è noto al chiamante.
        """
        await self.ensure_guild_exists(guild_id)

        # Leggiamo il valore PRIMA di sovrascriverlo: senza questo,
        # lo storico non avrebbe nulla da confrontare per un diff.
        old_row = await self.pool.fetchrow(
            "SELECT (modules -> $2)::boolean AS old_value FROM guild_config WHERE guild_id = $1",
            guild_id,
            module_name,
        )
        old_value = old_row["old_value"] if old_row is not None else None

        await self.pool.execute(
            """
            UPDATE guild_config
            SET modules = jsonb_set(modules, ARRAY[$2], to_jsonb($3::boolean)),
                updated_at = now()
            WHERE guild_id = $1
            """,
            guild_id,
            module_name,
            active,
        )
        # Invalida (non aggiorna in-place): alla prossima lettura la
        # cache si ripopola dal DB da zero, così non c'è mai il
        # rischio che una scrittura parziale lasci la cache
        # disallineata da quello che è realmente su disco.
        self._modules_cache.delete(guild_id)

        await self._record_config_change(
            guild_id, changed_by, "module", module_name, old_value, active
        )

    # ================================================================
    # Guild settings — configurazione libera per-modulo (JSONB)
    # ================================================================
    # A differenza di "modules" (solo True/False per ogni modulo),
    # "settings" tiene valori arbitrari: l'ID di un canale, un testo,
    # un numero. Ogni modulo usa una chiave propria (es.
    # "report_channel_id", "mute_role_id") per non calpestare le
    # impostazioni degli altri moduli.
    async def get_guild_setting(
        self, guild_id: int, key: str, default=None
    ):
        row = await self.pool.fetchrow(
            "SELECT settings -> $2 AS value FROM guild_config WHERE guild_id = $1",
            guild_id,
            key,
        )
        if row is None or row["value"] is None:
            return default
        # asyncpg restituisce il JSONB già come stringa JSON; lo
        # decodifichiamo per dare al chiamante il tipo Python atteso
        # (int, str, bool...) invece di una stringa JSON grezza.
        return json.loads(row["value"])

    async def set_guild_setting(
        self, guild_id: int, key: str, value, changed_by: int | None = None
    ) -> None:
        await self.ensure_guild_exists(guild_id)

        old_row = await self.pool.fetchrow(
            "SELECT settings -> $2 AS value FROM guild_config WHERE guild_id = $1",
            guild_id,
            key,
        )
        old_value = json.loads(old_row["value"]) if old_row and old_row["value"] is not None else None

        await self.pool.execute(
            """
            UPDATE guild_config
            SET settings = jsonb_set(settings, ARRAY[$2], $3::jsonb),
                updated_at = now()
            WHERE guild_id = $1
            """,
            guild_id,
            key,
            json.dumps(value),
        )

        await self._record_config_change(
            guild_id, changed_by, "setting", key, old_value, value
        )

    # ================================================================
    # Config Diff & Rollback (BACKLOG.md §11, estensione di SPEC.md §2.7)
    # ================================================================
    async def _record_config_change(
        self,
        guild_id: int,
        changed_by: int | None,
        change_type: str,
        key_name: str,
        old_value,
        new_value,
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO guild_config_history
                (guild_id, changed_by, change_type, key_name, old_value, new_value)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            guild_id,
            changed_by,
            change_type,
            key_name,
            json.dumps(old_value),
            json.dumps(new_value),
        )

    def _row_to_history_entry(self, row) -> ConfigHistoryEntry:
        return ConfigHistoryEntry(
            id=row["id"],
            guild_id=row["guild_id"],
            changed_by=row["changed_by"],
            change_type=row["change_type"],
            key_name=row["key_name"],
            old_value=json.loads(row["old_value"]) if row["old_value"] is not None else None,
            new_value=json.loads(row["new_value"]),
            created_at=row["created_at"],
        )

    async def get_config_history(
        self, guild_id: int, limit: int = 10
    ) -> list[ConfigHistoryEntry]:
        rows = await self.pool.fetch(
            """
            SELECT * FROM guild_config_history
            WHERE guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [self._row_to_history_entry(r) for r in rows]

    async def get_config_history_entry(self, entry_id: int) -> ConfigHistoryEntry | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM guild_config_history WHERE id = $1", entry_id
        )
        return self._row_to_history_entry(row) if row is not None else None

    async def rollback_config_change(self, entry_id: int, rolled_back_by: int | None) -> bool:
        """
        Ripristina old_value di una voce di storico. Restituisce
        False se la voce non esiste (nulla da ripristinare). Il
        rollback stesso viene registrato come una NUOVA voce di
        storico (tramite set_module_active_for_guild/
        set_guild_setting, non scritto direttamente qui) — un
        rollback lascia traccia di sé, non sparisce silenziosamente
        dalla cronologia.
        """
        entry = await self.get_config_history_entry(entry_id)
        if entry is None:
            return False

        if entry.change_type == "module":
            # old_value per un modulo è sempre bool o None (mai stato
            # attivato prima = tratta come False, non c'è un "modulo
            # in stato indefinito" sensato da ripristinare).
            valore_da_ripristinare = bool(entry.old_value)
            await self.set_module_active_for_guild(
                entry.guild_id, entry.key_name, valore_da_ripristinare, changed_by=rolled_back_by
            )
        else:
            await self.set_guild_setting(
                entry.guild_id, entry.key_name, entry.old_value, changed_by=rolled_back_by
            )
        return True

    # ================================================================
    # Premium whitelist
    # ================================================================
    async def is_guild_whitelisted(self, guild_id: int) -> bool:
        row = await self.pool.fetchrow(
            "SELECT 1 FROM premium_whitelist WHERE guild_id = $1",
            guild_id,
        )
        return row is not None

    async def add_guild_to_whitelist(
        self, guild_id: int, added_by: int, reason: str | None = None
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO premium_whitelist (guild_id, added_by, reason)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET added_by = EXCLUDED.added_by,
                    reason = EXCLUDED.reason
            """,
            guild_id,
            added_by,
            reason,
        )

    async def remove_guild_from_whitelist(self, guild_id: int) -> None:
        await self.pool.execute(
            "DELETE FROM premium_whitelist WHERE guild_id = $1",
            guild_id,
        )


# Istanza unica, condivisa da tutto il progetto.
db = Database()


# ====================================================================
# NOTA SULLA CRESCITA DI QUESTO FILE
# ====================================================================
# Man mano che si aggiungono moduli (moderation, leveling, gilde...),
# le loro tabelle e i loro metodi NON vanno tutti ammassati qui
# dentro: questo file resta per Database/Premium/Config di base.
# Ogni modulo avrà il proprio repository, es.:
#
#   core/repositories/moderation_repo.py
#   core/repositories/leveling_repo.py
#
# ognuno con il proprio run_migrations() (chiamato in sequenza
# dal main.py) e i propri metodi, ma tutti condividono lo stesso
# pool tramite `db.pool`. Questo tiene il file principale piccolo
# e ogni repository leggibile per il modulo a cui appartiene.
