"""
core/repositories/backup_sincronia_repo.py
==========================================
Le coppie di server in sincronia (ban e ruoli), al massimo 5 per server.
Funzioni coperte: SPEC §11.16, NF-39
"""

from __future__ import annotations

from dataclasses import dataclass

from core.server_sync_logic import MAX_SINCRONIE_PER_SERVER, coppia


@dataclass(frozen=True)
class Sincronia:
    altro: int
    ban: bool
    ruoli: bool


class BackupSincroniaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    async def attiva(self, guild_id: int, altro_id: int, ban: bool, ruoli: bool, created_by: int) -> bool:
        """Crea o aggiorna la coppia. False se uno dei due server ha già 5 sincronie."""
        a, b = coppia(guild_id, altro_id)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('backup_sincronie'))")
            esiste = await conn.fetchval(
                "SELECT 1 FROM backup_sincronie WHERE guild_a = $1 AND guild_b = $2", a, b
            )
            if not esiste:
                for g in (a, b):
                    quante = await conn.fetchval(
                        "SELECT count(*) FROM backup_sincronie WHERE guild_a = $1 OR guild_b = $1", g
                    )
                    if quante >= MAX_SINCRONIE_PER_SERVER:
                        return False
            await conn.execute(
                "INSERT INTO backup_sincronie (guild_a, guild_b, ban, ruoli, created_by) VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (guild_a, guild_b) DO UPDATE SET ban = EXCLUDED.ban, ruoli = EXCLUDED.ruoli",
                a, b, ban, ruoli, created_by,
            )
        return True

    async def disattiva(self, guild_id: int, altro_id: int) -> bool:
        a, b = coppia(guild_id, altro_id)
        esito = await self._pool.execute(
            "DELETE FROM backup_sincronie WHERE guild_a = $1 AND guild_b = $2", a, b
        )
        return esito.endswith(" 1")

    async def sincronie_di(self, guild_id: int) -> list[Sincronia]:
        righe = await self._pool.fetch(
            "SELECT CASE WHEN guild_a = $1 THEN guild_b ELSE guild_a END AS altro, ban, ruoli "
            "FROM backup_sincronie WHERE guild_a = $1 OR guild_b = $1",
            guild_id,
        )
        return [Sincronia(**dict(r)) for r in righe]


def _get_pool():
    from core.database import db

    return db.pool


backup_sincronia_repo = BackupSincroniaRepository(pool_provider=_get_pool)
