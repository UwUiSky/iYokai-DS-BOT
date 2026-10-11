"""
core/repositories/guild_presence_repo.py
========================================
Quando il bot è entrato e uscito da ogni server (tabella `guild_presence`,
migrazione 0034). L'uscita avvia i 90 giorni dopo i quali il lavoro giornaliero
cancella i dati del server (D6); un rientro prima non perde niente.
Funzioni coperte: SPEC §19 (NF-04)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg

from core.data_registry import GIORNI_DOPO_USCITA


class GuildPresenceRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def segna_entrato(self, guild_id: int) -> None:
        """Il bot è nel server. Dopo una cancellazione già fatta riparte da zero."""
        await self._pool.execute(
            """
            INSERT INTO guild_presence (guild_id) VALUES ($1)
            ON CONFLICT (guild_id) DO UPDATE SET
                left_at = NULL,
                joined_at = CASE WHEN guild_presence.purged_at IS NOT NULL
                                 THEN now() ELSE guild_presence.joined_at END,
                purged_at = NULL
            """,
            guild_id,
        )

    async def segna_uscito(self, guild_id: int, quando: datetime | None = None) -> None:
        """Il bot è uscito: avvia i 90 giorni (se erano già avviati restano quelli)."""
        await self._pool.execute(
            """
            INSERT INTO guild_presence (guild_id, left_at) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET
                left_at = COALESCE(guild_presence.left_at, EXCLUDED.left_at)
            """,
            guild_id,
            quando or datetime.now(timezone.utc),
        )

    async def sincronizza(self, guild_ids: set[int]) -> int:
        """
        All'avvio: i server in cui il bot è davvero sono "entrati", quelli che il
        database ricorda ma il bot non vede più sono "usciti" (parte il conto dei
        90 giorni). Restituisce quanti ha segnato usciti.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO guild_presence (guild_id) SELECT unnest($1::bigint[])
                    ON CONFLICT (guild_id) DO UPDATE SET left_at = NULL
                    WHERE guild_presence.left_at IS NOT NULL AND guild_presence.purged_at IS NULL
                    """,
                    list(guild_ids),
                )
                righe = await conn.fetch(
                    """
                    UPDATE guild_presence SET left_at = now()
                    WHERE left_at IS NULL AND purged_at IS NULL AND NOT (guild_id = ANY($1::bigint[]))
                    RETURNING guild_id
                    """,
                    list(guild_ids),
                )
        return len(righe)

    async def da_cancellare(
        self, adesso: datetime | None = None, giorni: int = GIORNI_DOPO_USCITA
    ) -> list[int]:
        """I server usciti da più di `giorni` e non ancora cancellati."""
        soglia = (adesso or datetime.now(timezone.utc)) - timedelta(days=giorni)
        righe = await self._pool.fetch(
            "SELECT guild_id FROM guild_presence "
            "WHERE left_at IS NOT NULL AND left_at < $1 AND purged_at IS NULL ORDER BY left_at",
            soglia,
        )
        return [r["guild_id"] for r in righe]

    async def segna_cancellato(self, guild_id: int, conn: asyncpg.Connection | None = None) -> None:
        corpo = "UPDATE guild_presence SET purged_at = now() WHERE guild_id = $1"
        if conn is not None:
            await conn.execute(corpo, guild_id)
        else:
            await self._pool.execute(corpo, guild_id)

    async def get(self, guild_id: int) -> dict | None:
        riga = await self._pool.fetchrow("SELECT * FROM guild_presence WHERE guild_id = $1", guild_id)
        return dict(riga) if riga else None


def _get_pool():
    from core.database import db

    return db.pool


guild_presence_repo = GuildPresenceRepository(pool_provider=_get_pool)
