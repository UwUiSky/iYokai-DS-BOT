"""
core/repositories/backup_repo.py
================================
Persistenza del Backup System: coppie main/backup (`backup_pairs`, una
riga per server main) e coda serializzata dei job di clonazione
(`backup_jobs`, timeout 24 ore).
Funzioni coperte: SPEC §11.1, §11.2, §11.12
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

# Stati possibili di un job — stringhe semplici invece di un ENUM
# Postgres, per poter aggiungere stati futuri senza una migration
# ALTER TYPE (che su Postgres è più delicata di quanto sembri).
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_TIMED_OUT = "timed_out"

TIMEOUT_HOURS = 24


@dataclass(frozen=True)
class BackupPair:
    main_guild_id: int
    backup_guild_id: int | None
    updated_at: datetime


@dataclass(frozen=True)
class BackupJob:
    id: int
    main_guild_id: int
    backup_guild_id: int | None
    status: str
    error_message: str | None
    reminder_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS backup_pairs (
            main_guild_id    BIGINT PRIMARY KEY,
            backup_guild_id  BIGINT,
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS backup_jobs (
            id               SERIAL PRIMARY KEY,
            main_guild_id    BIGINT NOT NULL,
            backup_guild_id  BIGINT,
            status           TEXT NOT NULL DEFAULT 'pending',
            error_message    TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- ADD COLUMN IF NOT EXISTS (idempotente, sicuro da rilanciare
        -- a ogni avvio): backup_jobs esisteva già prima che i
        -- promemoria fossero aggiunti, serve poterla estendere anche
        -- su un database già popolato, non solo alla prima creazione.
        ALTER TABLE backup_jobs ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMPTZ;

        CREATE INDEX IF NOT EXISTS idx_backup_jobs_status_created
            ON backup_jobs (status, created_at);
        """
    )


class BackupRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_pair(self, row) -> BackupPair:
        return BackupPair(
            main_guild_id=row["main_guild_id"],
            backup_guild_id=row["backup_guild_id"],
            updated_at=row["updated_at"],
        )

    def _row_to_job(self, row) -> BackupJob:
        return BackupJob(
            id=row["id"],
            main_guild_id=row["main_guild_id"],
            backup_guild_id=row["backup_guild_id"],
            status=row["status"],
            error_message=row["error_message"],
            reminder_sent_at=row["reminder_sent_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ----------------------------------------------------------------
    # Abbinamenti main/backup (§11.12)
    # ----------------------------------------------------------------
    async def define_main(self, main_guild_id: int) -> None:
        """Registra un server come 'main' — senza ancora un backup
        associato (NULL), se non esisteva già una riga per questo
        server. Se esisteva già, non tocca il backup_guild_id
        esistente (evita di cancellare un abbinamento già fatto
        rilanciando /admin backup main per errore)."""
        await self._pool.execute(
            """
            INSERT INTO backup_pairs (main_guild_id, backup_guild_id)
            VALUES ($1, NULL)
            ON CONFLICT (main_guild_id) DO UPDATE SET updated_at = now()
            """,
            main_guild_id,
        )

    async def define_backup(self, main_guild_id: int, backup_guild_id: int, conn=None) -> None:
        await (conn or self._pool).execute(
            """
            INSERT INTO backup_pairs (main_guild_id, backup_guild_id)
            VALUES ($1, $2)
            ON CONFLICT (main_guild_id) DO UPDATE
                SET backup_guild_id = EXCLUDED.backup_guild_id, updated_at = now()
            """,
            main_guild_id,
            backup_guild_id,
        )

    async def get_pair(self, main_guild_id: int) -> BackupPair | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM backup_pairs WHERE main_guild_id = $1", main_guild_id
        )
        return self._row_to_pair(row) if row is not None else None

    async def get_pair_by_backup_guild_id(self, backup_guild_id: int) -> BackupPair | None:
        """Trova la coppia partendo dal server BACKUP (l'inverso di
        get_pair, che parte dal main) — serve a /admin backup promuovi per
        capire "di quale main ero il backup" quando il comando viene
        lanciato dentro al server backup stesso (SPEC.md §11.13)."""
        row = await self._pool.fetchrow(
            "SELECT * FROM backup_pairs WHERE backup_guild_id = $1", backup_guild_id
        )
        return self._row_to_pair(row) if row is not None else None

    async def is_backup_of(self, main_guild_id: int, guild_id: int) -> bool:
        """True se guild_id è il backup registrato di main_guild_id, oggi o
        prima di una promozione (coppia storica, BUG-34)."""
        coppia = await self.get_pair(main_guild_id)
        if coppia is not None and coppia.backup_guild_id == guild_id:
            return True
        storica = await self._pool.fetchval(
            "SELECT 1 FROM backup_pair_history WHERE old_main_guild_id = $1 AND promoted_guild_id = $2",
            main_guild_id,
            guild_id,
        )
        return storica is not None

    async def promote_backup_to_main(self, old_main_guild_id: int, new_main_guild_id: int) -> None:
        """
        Promuove un server backup a nuovo main (SPEC.md §11.13) —
        usata quando il main originale è perso/inutilizzabile e il
        backup deve prendere il suo posto:

        1. Il vecchio main perde il suo backup (backup_guild_id = NULL)
           — non lo cancelliamo dalla tabella: potrebbe ancora esistere
           e volere un nuovo backup più avanti, ma di certo non è più
           abbinato a QUESTO server (che ora è main altrove).
        2. Il server appena promosso diventa main a sua volta, SENZA
           backup (NULL) — l'auto-propagazione (enqueue di un nuovo
           job) è responsabilità del chiamante, qui c'è solo lo stato.

        Le due UPDATE sono nella stessa connessione/transazione per
        evitare uno stato intermedio inconsistente se una fallisce.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # BUG-34: la coppia storica resta, altrimenti /admin backup
                # restore-utenti rifiuta il server appena promosso.
                await conn.execute(
                    """
                    INSERT INTO backup_pair_history (old_main_guild_id, promoted_guild_id)
                    VALUES ($1, $2) ON CONFLICT DO NOTHING
                    """,
                    old_main_guild_id,
                    new_main_guild_id,
                )
                await conn.execute(
                    "UPDATE backup_pairs SET backup_guild_id = NULL, updated_at = now() "
                    "WHERE main_guild_id = $1",
                    old_main_guild_id,
                )
                await conn.execute(
                    """
                    INSERT INTO backup_pairs (main_guild_id, backup_guild_id)
                    VALUES ($1, NULL)
                    ON CONFLICT (main_guild_id) DO UPDATE
                        SET backup_guild_id = NULL, updated_at = now()
                    """,
                    new_main_guild_id,
                )

    # ----------------------------------------------------------------
    # Coda job (§11.2)
    # ----------------------------------------------------------------
    async def enqueue_linked_job(self, main_guild_id: int, backup_guild_id: int, conn=None) -> int:
        """Job già legato al server di backup (D8): il Creator lo trova da solo."""
        return await (conn or self._pool).fetchval(
            """
            INSERT INTO backup_jobs (main_guild_id, backup_guild_id, status)
            VALUES ($1, $2, $3) RETURNING id
            """,
            main_guild_id,
            backup_guild_id,
            STATUS_PENDING,
        )

    # ----------------------------------------------------------------
    # Codici di collegamento (M 12.1)
    # ----------------------------------------------------------------
    async def salva_codice_collegamento(
        self, main_guild_id: int, code_hash: str, creato_da: int, scadenza: datetime
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO backup_link_codes (main_guild_id, code_hash, created_by, expires_at)
            VALUES ($1, $2, $3, $4)
            """,
            main_guild_id,
            code_hash,
            creato_da,
            scadenza,
        )

    async def trova_codice_collegamento(self, code_hash: str):
        return await self._pool.fetchrow(
            "SELECT main_guild_id, created_by, expires_at, used_at FROM backup_link_codes WHERE code_hash = $1",
            code_hash,
        )

    async def collega_atomico(
        self, code_hash: str, backup_guild_id: int, adesso: datetime
    ) -> tuple[str, int | None, int | None]:
        """
        Tutto o niente, in una transazione: controlla il codice, brucia il codice,
        scrive la coppia e mette il job in coda. Se una scrittura fallisce il codice
        resta buono. Un blocco per server evita due collegamenti insieme.
        Restituisce (esito, main_guild_id, job_id).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                riga = await conn.fetchrow(
                    "SELECT main_guild_id, expires_at, used_at FROM backup_link_codes "
                    "WHERE code_hash = $1 FOR UPDATE",
                    code_hash,
                )
                if riga is None:
                    return ("sconosciuto", None, None)
                main = riga["main_guild_id"]
                if riga["used_at"] is not None:
                    return ("gia_usato", main, None)
                if riga["expires_at"] <= adesso:
                    return ("scaduto", main, None)
                if main == backup_guild_id:
                    return ("stesso_server", main, None)

                await conn.execute("SELECT pg_advisory_xact_lock($1)", main)
                attivo = await conn.fetchval(
                    "SELECT 1 FROM backup_jobs WHERE main_guild_id = $1 AND status IN ($2, $3) LIMIT 1",
                    main, STATUS_PENDING, STATUS_RUNNING,
                )
                if attivo is not None:
                    return ("gia_collegato", main, None)
                occupato = await conn.fetchval(
                    """
                    SELECT 1 FROM backup_pairs
                    WHERE backup_guild_id IS NOT NULL AND (
                          (backup_guild_id = $2 AND main_guild_id <> $1)   -- già backup di un altro
                       OR (main_guild_id = $2)                             -- è già un main con backup
                       OR (main_guild_id = $1 AND backup_guild_id <> $2)   -- il main ha un altro backup
                    ) LIMIT 1
                    """,
                    main, backup_guild_id,
                )
                if occupato is not None:
                    return ("gia_collegato", main, None)

                await conn.execute(
                    "UPDATE backup_link_codes SET used_at = $2 WHERE code_hash = $1", code_hash, adesso
                )
                await self.define_backup(main, backup_guild_id, conn=conn)
                job_id = await self.enqueue_linked_job(main, backup_guild_id, conn=conn)
                return ("ok", main, job_id)

    async def rimuovi_coppia(self, main_guild_id: int, backup_guild_id: int) -> None:
        """Una copia fallita non deve lasciare un server vuoto registrato come backup."""
        await self._pool.execute(
            "UPDATE backup_pairs SET backup_guild_id = NULL, updated_at = now() "
            "WHERE main_guild_id = $1 AND backup_guild_id = $2",
            main_guild_id, backup_guild_id,
        )

    async def has_active_job(self, main_guild_id: int) -> bool:
        """True se il server ha già un job in attesa o in corso."""
        riga = await self._pool.fetchval(
            "SELECT 1 FROM backup_jobs WHERE main_guild_id = $1 AND status IN ($2, $3) LIMIT 1",
            main_guild_id,
            STATUS_PENDING,
            STATUS_RUNNING,
        )
        return riga is not None

    async def expire_stale_jobs(self) -> int:
        """
        Marca come 'timed_out' ogni job ancora pending/running più
        vecchio di TIMEOUT_HOURS — un job bloccato (crash a metà,
        errore mai gestito) non deve restare "in corso" per sempre,
        bloccando la coda a tutti gli altri. Restituisce quanti ne
        sono stati scaduti, utile per il log del chiamante.
        """
        risultato = await self._pool.execute(
            """
            UPDATE backup_jobs
            SET status = $1, updated_at = now()
            WHERE status IN ($2, $3)
              AND created_at < now() - ($4 || ' hours')::interval
            """,
            STATUS_TIMED_OUT,
            STATUS_PENDING,
            STATUS_RUNNING,
            str(TIMEOUT_HOURS),
        )
        # "UPDATE N" -> N
        return int(risultato.split()[-1])

    async def get_next_pending_job(self) -> BackupJob | None:
        """Il job pending più vecchio (FIFO) — coda SERIALIZZATA, un
        solo job alla volta viene eseguito. Non marca nulla da solo:
        chi chiama deve poi mark_running() esplicitamente."""
        row = await self._pool.fetchrow(
            """
            SELECT * FROM backup_jobs
            WHERE status = $1
            ORDER BY created_at ASC
            LIMIT 1
            """,
            STATUS_PENDING,
        )
        return self._row_to_job(row) if row is not None else None

    async def mark_running(self, job_id: int) -> None:
        await self._pool.execute(
            "UPDATE backup_jobs SET status = $2, updated_at = now() WHERE id = $1",
            job_id,
            STATUS_RUNNING,
        )

    async def mark_completed(self, job_id: int, backup_guild_id: int) -> None:
        await self._pool.execute(
            """
            UPDATE backup_jobs
            SET status = $2, backup_guild_id = $3, updated_at = now()
            WHERE id = $1
            """,
            job_id,
            STATUS_COMPLETED,
            backup_guild_id,
        )

    async def mark_failed(self, job_id: int, error_message: str) -> None:
        await self._pool.execute(
            """
            UPDATE backup_jobs
            SET status = $2, error_message = $3, updated_at = now()
            WHERE id = $1
            """,
            job_id,
            STATUS_FAILED,
            error_message,
        )

    async def get_job(self, job_id: int) -> BackupJob | None:
        row = await self._pool.fetchrow("SELECT * FROM backup_jobs WHERE id = $1", job_id)
        return self._row_to_job(row) if row is not None else None

    async def get_all_main_guild_ids_with_backup(self) -> list[int]:
        """
        Tutti i main_guild_id che hanno GIÀ un backup attivo
        (backup_guild_id NOT NULL) — usata dallo snapshot settimanale
        utenti (SPEC.md §11.10): non ha senso fotografare gli utenti
        di un server che non ha ancora nemmeno un backup dove
        eventualmente restaurarli.
        """
        rows = await self._pool.fetch(
            "SELECT main_guild_id FROM backup_pairs WHERE backup_guild_id IS NOT NULL"
        )
        return [r["main_guild_id"] for r in rows]

    async def get_job_by_backup_guild_id(self, backup_guild_id: int) -> BackupJob | None:
        """Usata dal listener che reagisce a Main che entra in un
        server nuovo — per sapere se QUEL server è il backup atteso
        da un job in corso, o un server qualsiasi in cui Main è
        stato invitato per altri motivi."""
        row = await self._pool.fetchrow(
            "SELECT * FROM backup_jobs WHERE backup_guild_id = $1 ORDER BY id DESC LIMIT 1",
            backup_guild_id,
        )
        return self._row_to_job(row) if row is not None else None


def _get_pool():
    from core.database import db
    return db.pool


backup_repo = BackupRepository(pool_provider=_get_pool)
