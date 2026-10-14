"""
core/repositories/modmail_repo.py
=================================
Conversazioni ModMail (un canale dello staff per utente) e utenti bloccati.
Funzioni coperte: SPEC §23 (NF-33)
Tabelle: migrazione 0101 (`modmail_threads`, `modmail_blocks`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

ONE_OPEN_INDEX = "uq_modmail_un_aperto_per_utente"


class ConversazioneGiaAperta(Exception):
    """L'utente ha già una conversazione ModMail aperta."""


@dataclass(frozen=True)
class ModmailThread:
    id: int
    guild_id: int
    user_id: int
    channel_id: int
    status: str
    created_at: datetime
    closed_at: datetime | None
    closed_by: int | None
    close_reason: str | None


def _thread(r) -> ModmailThread:
    return ModmailThread(
        id=r["id"], guild_id=r["guild_id"], user_id=r["user_id"], channel_id=r["channel_id"],
        status=r["status"], created_at=r["created_at"], closed_at=r["closed_at"],
        closed_by=r["closed_by"], close_reason=r["close_reason"],
    )


class ModmailRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def crea(self, guild_id: int, user_id: int, channel_id: int) -> ModmailThread:
        try:
            riga = await self._pool.fetchrow(
                "INSERT INTO modmail_threads (guild_id, user_id, channel_id) VALUES ($1, $2, $3) RETURNING *",
                guild_id, user_id, channel_id,
            )
        except asyncpg.UniqueViolationError as errore:
            if errore.constraint_name == ONE_OPEN_INDEX:
                raise ConversazioneGiaAperta() from errore
            raise
        return _thread(riga)

    async def aperta_dell_utente(self, user_id: int) -> ModmailThread | None:
        riga = await self._pool.fetchrow(
            "SELECT * FROM modmail_threads WHERE user_id = $1 AND status = 'open'", user_id
        )
        return _thread(riga) if riga else None

    async def aperta_del_canale(self, channel_id: int) -> ModmailThread | None:
        riga = await self._pool.fetchrow(
            "SELECT * FROM modmail_threads WHERE channel_id = $1 AND status = 'open'", channel_id
        )
        return _thread(riga) if riga else None

    async def aperta_dell_utente_nel_server(self, guild_id: int, user_id: int) -> ModmailThread | None:
        riga = await self._pool.fetchrow(
            "SELECT * FROM modmail_threads WHERE guild_id = $1 AND user_id = $2 AND status = 'open'",
            guild_id, user_id,
        )
        return _thread(riga) if riga else None

    async def chiudi(self, channel_id: int, closed_by: int | None, reason: str | None = None) -> bool:
        esito = await self._pool.execute(
            """
            UPDATE modmail_threads
            SET status = 'closed', closed_at = now(), closed_by = $2, close_reason = $3
            WHERE channel_id = $1 AND status = 'open'
            """,
            channel_id, closed_by, reason,
        )
        return esito.endswith(" 1")

    async def riapri_dopo_errore(self, channel_id: int) -> bool:
        """Annulla una chiusura appena fatta (eliminazione non pianificabile). False se non si può più riaprire."""
        try:
            esito = await self._pool.execute(
                """
                UPDATE modmail_threads
                SET status = 'open', closed_at = NULL, closed_by = NULL, close_reason = NULL
                WHERE channel_id = $1 AND status = 'closed'
                """,
                channel_id,
            )
        except asyncpg.UniqueViolationError:
            return False  # nel frattempo l'utente ha già un'altra conversazione aperta
        return esito.endswith(" 1")

    async def categoria(self, guild_id: int) -> int | None:
        """La categoria dei canali dello staff; None = ModMail spento."""
        return await self._pool.fetchval(
            "SELECT category_id FROM modmail_config WHERE guild_id = $1", guild_id
        )

    async def imposta_categoria(self, guild_id: int, category_id: int | None, by: int | None = None) -> None:
        if category_id is None:
            await self._pool.execute("DELETE FROM modmail_config WHERE guild_id = $1", guild_id)
            return
        await self._pool.execute(
            """
            INSERT INTO modmail_config (guild_id, category_id, updated_by) VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET category_id = $2, updated_by = $3, updated_at = now()
            """,
            guild_id, category_id, by,
        )

    async def blocca(self, guild_id: int, user_id: int, by: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO modmail_blocks (guild_id, user_id, blocked_by) VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO NOTHING
            """,
            guild_id, user_id, by,
        )

    async def sblocca(self, guild_id: int, user_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM modmail_blocks WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return esito.endswith(" 1")

    async def bloccato(self, guild_id: int, user_id: int) -> bool:
        return bool(
            await self._pool.fetchval(
                "SELECT 1 FROM modmail_blocks WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
            )
        )


def _get_pool():
    from core.database import db
    return db.pool


modmail_repo = ModmailRepository(pool_provider=_get_pool)
