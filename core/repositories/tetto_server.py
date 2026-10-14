"""
core/repositories/tetto_server.py
=================================
Tetto "al massimo N per server" che regge anche a richieste in parallelo.
`INSERT ... WHERE (SELECT count(*)) < N` da solo NON basta: due transazioni insieme vedono lo
stesso conteggio e passano entrambe. Qui conteggio e scrittura stanno nella stessa transazione,
dietro un lock advisory per (tabella, server): chi arriva secondo aspetta e vede il conteggio vero.
"""

from __future__ import annotations

from contextlib import asynccontextmanager


@asynccontextmanager
async def tetto_per_server(pool, tabella: str, guild_id: int):
    """Dà una connessione dentro una transazione con il lock del server già preso."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1), $2)", tabella, guild_id % 2_147_483_647
            )
            yield conn
