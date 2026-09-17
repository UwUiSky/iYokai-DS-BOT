"""
core/repositories/spam_trap_repo.py
======================================
Persistenza dello Spam Trap: canali configurati, indice dei messaggi
(solo id/canale/timestamp — MAI il contenuto, vedi la nota
architetturale in core/spam_trap_logic.py), cooldown degli appeal,
e i dettagli di ogni incidente (per il log e il transcript).

Il case del ban vero e proprio (chi, quando, motivo) vive nella
tabella moderation_cases già esistente — riusata, non duplicata:
uno Spam Trap ban è semplicemente un caso con
action_type="spam_trap_ban" (vedi cogs/security/spam_trap.py). Qui
c'è solo il contesto AGGIUNTIVO che moderation_cases non ha
(contenuto catturato, invito, conteggio messaggi cancellati).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class SpamTrapConfig:
    guild_id: int
    trap_channel_id: int | None
    log_channel_id: int | None


@dataclass(frozen=True)
class IndexedMessage:
    message_id: int
    channel_id: int
    created_at: datetime


@dataclass(frozen=True)
class SpamTrapIncident:
    id: int
    guild_id: int
    case_number: int
    trapped_content: str
    invite_code: str | None
    invite_creator_id: int | None
    deleted_count_by_channel: dict[str, int]
    transcript_html: str | None
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS spam_trap_config (
            guild_id        BIGINT PRIMARY KEY,
            trap_channel_id BIGINT,
            log_channel_id  BIGINT
        );

        -- Indice di TUTTI i messaggi (non solo quelli nel canale
        -- trappola) dei server con questo modulo attivo — solo per
        -- sapere COSA cancellare in caso di ban, mai il contenuto.
        CREATE TABLE IF NOT EXISTS spam_trap_message_index (
            message_id BIGINT PRIMARY KEY,
            guild_id   BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            user_id    BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );

        -- La query che conta: "messaggi di questo utente in questo
        -- server, in una finestra di tempo" — esattamente quello che
        -- la purge supplementare interroga ad ogni ban.
        CREATE INDEX IF NOT EXISTS idx_spam_trap_index_user_time
            ON spam_trap_message_index (guild_id, user_id, created_at);

        -- Per la pulizia periodica (prune_old_index): trovare le
        -- righe più vecchie di 30 giorni senza scansionare tutto.
        CREATE INDEX IF NOT EXISTS idx_spam_trap_index_created_at
            ON spam_trap_message_index (created_at);

        CREATE TABLE IF NOT EXISTS spam_trap_appeals (
            guild_id       BIGINT NOT NULL,
            user_id        BIGINT NOT NULL,
            last_appeal_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS spam_trap_incidents (
            id                       SERIAL PRIMARY KEY,
            guild_id                 BIGINT NOT NULL,
            case_number              INTEGER NOT NULL,
            trapped_content          TEXT NOT NULL DEFAULT '',
            invite_code              TEXT,
            invite_creator_id        BIGINT,
            deleted_count_by_channel JSONB NOT NULL DEFAULT '{}'::jsonb,
            transcript_html          TEXT,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (guild_id, case_number)
        );

        -- Se la tabella esisteva già da prima di questa colonna
        -- (stesso pattern già usato per guild_config.settings):
        -- aggiunta sicura da rieseguire ad ogni avvio.
        ALTER TABLE spam_trap_incidents
            ADD COLUMN IF NOT EXISTS transcript_html TEXT;

        -- L'invito usato per entrare va catturato AL MOMENTO DEL
        -- JOIN (via core/invite_tracker.py) perché al momento di un
        -- eventuale ban, molto più tardi, non è più possibile
        -- risalirci: la cache degli inviti nel frattempo è cambiata.
        -- Una riga per join (non un semplice upsert per utente):
        -- se un utente esce e rientra, ogni join ha il suo invito.
        CREATE TABLE IF NOT EXISTS spam_trap_join_invites (
            id                 SERIAL PRIMARY KEY,
            guild_id           BIGINT NOT NULL,
            user_id            BIGINT NOT NULL,
            invite_code        TEXT,
            invite_creator_id  BIGINT,
            joined_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_spam_trap_join_invites_lookup
            ON spam_trap_join_invites (guild_id, user_id, joined_at DESC);
        """
    )


class SpamTrapRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ================================================================
    # Configurazione
    # ================================================================
    async def get_config(self, guild_id: int) -> SpamTrapConfig:
        row = await self._pool.fetchrow(
            "SELECT trap_channel_id, log_channel_id FROM spam_trap_config WHERE guild_id = $1",
            guild_id,
        )
        if row is None:
            return SpamTrapConfig(guild_id, None, None)
        return SpamTrapConfig(guild_id, row["trap_channel_id"], row["log_channel_id"])

    async def set_config(
        self, guild_id: int, trap_channel_id: int, log_channel_id: int
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO spam_trap_config (guild_id, trap_channel_id, log_channel_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET trap_channel_id = EXCLUDED.trap_channel_id,
                    log_channel_id = EXCLUDED.log_channel_id
            """,
            guild_id,
            trap_channel_id,
            log_channel_id,
        )

    # ================================================================
    # Indice messaggi (per la purge supplementare)
    # ================================================================
    async def index_message(
        self, message_id: int, guild_id: int, channel_id: int, user_id: int, created_at: datetime
    ) -> None:
        # ON CONFLICT DO NOTHING: idempotente, non dovrebbe mai
        # capitare un message_id duplicato (sono snowflake univoci di
        # Discord), ma un doppio evento accidentale non deve far
        # fallire l'indicizzazione.
        await self._pool.execute(
            """
            INSERT INTO spam_trap_message_index (message_id, guild_id, channel_id, user_id, created_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (message_id) DO NOTHING
            """,
            message_id,
            guild_id,
            channel_id,
            user_id,
            created_at,
        )

    async def get_user_messages_in_window(
        self, guild_id: int, user_id: int, start: datetime, end: datetime
    ) -> list[IndexedMessage]:
        rows = await self._pool.fetch(
            """
            SELECT message_id, channel_id, created_at FROM spam_trap_message_index
            WHERE guild_id = $1 AND user_id = $2
              AND created_at >= $3 AND created_at <= $4
            ORDER BY created_at
            """,
            guild_id,
            user_id,
            start,
            end,
        )
        return [
            IndexedMessage(r["message_id"], r["channel_id"], r["created_at"]) for r in rows
        ]

    async def get_all_user_messages(
        self, guild_id: int, user_id: int
    ) -> list[IndexedMessage]:
        """Usato per il transcript: TUTTI i messaggi indicizzati
        dell'utente in questo server, non solo la finestra di purge."""
        rows = await self._pool.fetch(
            """
            SELECT message_id, channel_id, created_at FROM spam_trap_message_index
            WHERE guild_id = $1 AND user_id = $2
            ORDER BY created_at
            """,
            guild_id,
            user_id,
        )
        return [
            IndexedMessage(r["message_id"], r["channel_id"], r["created_at"]) for r in rows
        ]

    async def delete_indexed_messages(self, message_ids: list[int]) -> None:
        if not message_ids:
            return
        await self._pool.execute(
            "DELETE FROM spam_trap_message_index WHERE message_id = ANY($1::bigint[])",
            message_ids,
        )

    async def prune_old_index(self, older_than: datetime) -> int:
        """
        Cancella le righe di indice più vecchie della soglia data.
        Chiamata periodicamente (vedi core/scheduler.py) per tenere
        la tabella limitata invece di crescere all'infinito —
        serve solo agli ultimi 30 giorni, oltre non ha senso tenerla.
        Restituisce quante righe sono state eliminate.
        """
        result = await self._pool.execute(
            "DELETE FROM spam_trap_message_index WHERE created_at < $1",
            older_than,
        )
        # asyncpg restituisce una stringa tipo "DELETE 42"
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    # ================================================================
    # Invito usato al join (catturato subito, letto molto più tardi)
    # ================================================================
    async def record_join_invite(
        self,
        guild_id: int,
        user_id: int,
        invite_code: str | None,
        invite_creator_id: int | None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO spam_trap_join_invites (guild_id, user_id, invite_code, invite_creator_id)
            VALUES ($1, $2, $3, $4)
            """,
            guild_id,
            user_id,
            invite_code,
            invite_creator_id,
        )

    async def get_latest_join_invite(
        self, guild_id: int, user_id: int
    ) -> tuple[str | None, int | None] | None:
        """
        L'ultimo invito registrato per questo utente in questo
        server (se è entrato più volte, quello del join più recente
        — coerente con "l'invito con cui è entrato l'ultima volta",
        che è il join rilevante per un ban che avviene ora).
        """
        row = await self._pool.fetchrow(
            """
            SELECT invite_code, invite_creator_id FROM spam_trap_join_invites
            WHERE guild_id = $1 AND user_id = $2
            ORDER BY joined_at DESC LIMIT 1
            """,
            guild_id,
            user_id,
        )
        if row is None:
            return None
        return row["invite_code"], row["invite_creator_id"]

    # ================================================================
    # Appeal
    # ================================================================
    async def get_last_appeal(self, guild_id: int, user_id: int) -> datetime | None:
        return await self._pool.fetchval(
            "SELECT last_appeal_at FROM spam_trap_appeals WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )

    async def set_last_appeal(self, guild_id: int, user_id: int, when: datetime) -> None:
        await self._pool.execute(
            """
            INSERT INTO spam_trap_appeals (guild_id, user_id, last_appeal_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET last_appeal_at = $3
            """,
            guild_id,
            user_id,
            when,
        )

    # ================================================================
    # Incidenti (contesto aggiuntivo di ogni ban, oltre al case)
    # ================================================================
    async def create_incident(
        self,
        guild_id: int,
        case_number: int,
        trapped_content: str,
        invite_code: str | None,
        invite_creator_id: int | None,
        deleted_count_by_channel: dict[str, int],
        transcript_html: str | None = None,
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO spam_trap_incidents
                (guild_id, case_number, trapped_content, invite_code,
                 invite_creator_id, deleted_count_by_channel, transcript_html)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            RETURNING id
            """,
            guild_id,
            case_number,
            trapped_content,
            invite_code,
            invite_creator_id,
            json.dumps(deleted_count_by_channel),
            transcript_html,
        )
        return row["id"]

    async def get_incident_by_case(
        self, guild_id: int, case_number: int
    ) -> SpamTrapIncident | None:
        row = await self._pool.fetchrow(
            """
            SELECT id, guild_id, case_number, trapped_content, invite_code,
                   invite_creator_id, deleted_count_by_channel, transcript_html, created_at
            FROM spam_trap_incidents WHERE guild_id = $1 AND case_number = $2
            """,
            guild_id,
            case_number,
        )
        if row is None:
            return None
        return SpamTrapIncident(
            id=row["id"],
            guild_id=row["guild_id"],
            case_number=row["case_number"],
            trapped_content=row["trapped_content"],
            invite_code=row["invite_code"],
            invite_creator_id=row["invite_creator_id"],
            deleted_count_by_channel=json.loads(row["deleted_count_by_channel"]),
            transcript_html=row["transcript_html"],
            created_at=row["created_at"],
        )


def _get_pool():
    from core.database import db
    return db.pool


spam_trap_repo = SpamTrapRepository(pool_provider=_get_pool)
