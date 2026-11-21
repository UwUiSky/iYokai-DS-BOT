"""
core/repositories/ticket_log_repo.py
====================================
Gli interruttori del log delle azioni sui ticket (TKT-076): una riga per server e azione; senza riga l'azione è spenta.
Funzioni coperte: SPEC §13 (TKT-076)
Tabelle: migrazione 0772 (`ticket_log_azioni`).
"""

from __future__ import annotations

import asyncpg

from core.ticket_log_logic import AZIONI


class TicketLogRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def accese(self, guild_id: int) -> frozenset[str]:
        righe = await self._pool.fetch(
            "SELECT azione FROM ticket_log_azioni WHERE guild_id = $1 AND acceso", guild_id
        )
        return frozenset(r["azione"] for r in righe) & frozenset(AZIONI)

    async def imposta(self, guild_id: int, azioni: tuple[str, ...], acceso: bool) -> None:
        for azione in azioni:
            if azione not in AZIONI:
                raise ValueError(f"Azione sconosciuta: {azione}")
        await self._pool.executemany(
            """
            INSERT INTO ticket_log_azioni (guild_id, azione, acceso) VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, azione) DO UPDATE SET acceso = EXCLUDED.acceso
            """,
            [(guild_id, azione, acceso) for azione in azioni],
        )


def _get_pool():
    from core.database import db
    return db.pool


ticket_log_repo = TicketLogRepository(pool_provider=_get_pool)
