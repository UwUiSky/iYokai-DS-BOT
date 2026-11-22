"""
core/repositories/backup_automatico_repo.py
===========================================
Impostazione delle copie automatiche della struttura (ogni N ore, da 1 a 8 copie tenute).
Funzioni coperte: BKP-008
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

ORE_MINIME, ORE_MASSIME = 4, 168
COPIE_MINIME, COPIE_MASSIME = 1, 8


@dataclass(frozen=True)
class BackupAutomatico:
    guild_id: int
    ore: int
    copie: int
    ultimo: datetime | None


class BackupAutomaticoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    async def imposta(self, guild_id: int, ore: int, copie: int, user_id: int) -> None:
        if not (ORE_MINIME <= ore <= ORE_MASSIME and COPIE_MINIME <= copie <= COPIE_MASSIME):
            raise ValueError("ore o copie fuori dai limiti")
        await self._pool.execute(
            "INSERT INTO backup_automatici (guild_id, ore, copie, created_by) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (guild_id) DO UPDATE SET ore = $2, copie = $3, created_by = $4",
            guild_id, ore, copie, user_id,
        )

    async def togli(self, guild_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM backup_automatici WHERE guild_id = $1", guild_id)
        return esito.endswith(" 1")

    async def leggi(self, guild_id: int) -> BackupAutomatico | None:
        riga = await self._pool.fetchrow(
            "SELECT guild_id, ore, copie, ultimo FROM backup_automatici WHERE guild_id = $1", guild_id
        )
        return BackupAutomatico(**dict(riga)) if riga is not None else None

    async def prossimo_dovuto(self) -> BackupAutomatico | None:
        """Il server con la copia più in ritardo (mai fatta per prima)."""
        riga = await self._pool.fetchrow(
            "SELECT guild_id, ore, copie, ultimo FROM backup_automatici "
            "WHERE ultimo IS NULL OR ultimo + make_interval(hours => ore) <= now() "
            "ORDER BY ultimo NULLS FIRST LIMIT 1"
        )
        return BackupAutomatico(**dict(riga)) if riga is not None else None

    async def segna(self, guild_id: int) -> None:
        await self._pool.execute("UPDATE backup_automatici SET ultimo = now() WHERE guild_id = $1", guild_id)


def _get_pool():
    from core.database import db

    return db.pool


backup_automatico_repo = BackupAutomaticoRepository(pool_provider=_get_pool)
