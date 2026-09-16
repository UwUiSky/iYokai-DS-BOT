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

import asyncpg

from core.config import config


class Database:
    """
    Wrapper attorno al pool di connessioni.
    Un'unica istanza condivisa da tutto il bot (vedi `db` in fondo).
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

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
                    prefix          TEXT,
                    language        TEXT NOT NULL DEFAULT 'it',
                    setup_completed BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                );

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
                """
            )

        # Migrazioni degli altri sottosistemi core. Ognuno espone il
        # proprio run_migrations(pool) e viene chiamato qui in
        # sequenza — così ogni modulo resta responsabile del proprio
        # schema, ma c'è un solo punto che li invoca tutti in ordine
        # all'avvio del bot.
        from core.scheduler import run_migrations as scheduler_migrations
        await scheduler_migrations(self.pool)

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
        decidere se rispondere o ignorare un comando.
        """
        row = await self.pool.fetchrow(
            """
            SELECT (modules -> $2)::boolean AS is_active
            FROM guild_config
            WHERE guild_id = $1
            """,
            guild_id,
            module_name,
        )
        if row is None or row["is_active"] is None:
            return False
        return row["is_active"]

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
