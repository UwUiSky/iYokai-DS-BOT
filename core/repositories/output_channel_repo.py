"""
core/repositories/output_channel_repo.py
========================================
Tabella output_channels (server, tipo, canale, post, avviso già mandato).
Funzioni coperte: SPEC §18 (NF-01)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class OutputChannel:
    guild_id: int
    tipo: str
    channel_id: int
    post_id: int | None
    avvisato: bool


def _riga(row) -> OutputChannel:
    return OutputChannel(
        guild_id=row["guild_id"],
        tipo=row["tipo"],
        channel_id=row["channel_id"],
        post_id=row["post_id"],
        avvisato=row["avvisato"],
    )


class OutputChannelRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def imposta(self, guild_id: int, tipo: str, channel_id: int) -> None:
        """Sceglie il canale di un tipo. Azzera post e avviso."""
        await self._pool.execute(
            """
            INSERT INTO output_channels (guild_id, tipo, channel_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, tipo) DO UPDATE
                SET channel_id = EXCLUDED.channel_id, post_id = NULL, avvisato = FALSE
            """,
            guild_id, tipo, channel_id,
        )

    async def ottieni(self, guild_id: int, tipo: str) -> OutputChannel | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM output_channels WHERE guild_id = $1 AND tipo = $2",
            guild_id, tipo,
        )
        return _riga(row) if row else None

    async def elenco(self, guild_id: int) -> list[OutputChannel]:
        righe = await self._pool.fetch(
            "SELECT * FROM output_channels WHERE guild_id = $1 ORDER BY tipo", guild_id
        )
        return [_riga(r) for r in righe]

    async def rimuovi(self, guild_id: int, tipo: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM output_channels WHERE guild_id = $1 AND tipo = $2", guild_id, tipo
        )
        return esito.endswith(" 1")

    async def salva_post(self, guild_id: int, tipo: str, channel_id: int, post_id: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO output_channels (guild_id, tipo, channel_id, post_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, tipo) DO UPDATE SET post_id = EXCLUDED.post_id
            """,
            guild_id, tipo, channel_id, post_id,
        )

    async def segna_avvisato(self, guild_id: int, tipo: str, channel_id: int) -> bool:
        """True solo la prima volta: chi la riceve manda l'avviso."""
        row = await self._pool.fetchrow(
            """
            INSERT INTO output_channels (guild_id, tipo, channel_id, avvisato)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT (guild_id, tipo) DO UPDATE SET avvisato = TRUE
                WHERE NOT output_channels.avvisato
            RETURNING 1
            """,
            guild_id, tipo, channel_id,
        )
        return row is not None

    async def azzera_avviso(self, guild_id: int, tipo: str) -> None:
        await self._pool.execute(
            "UPDATE output_channels SET avvisato = FALSE WHERE guild_id = $1 AND tipo = $2",
            guild_id, tipo,
        )


def _get_pool():
    from core.database import db
    return db.pool


output_channel_repo = OutputChannelRepository(pool_provider=_get_pool)
