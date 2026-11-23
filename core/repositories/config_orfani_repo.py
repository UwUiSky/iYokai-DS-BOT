"""
core/repositories/config_orfani_repo.py
=======================================
Da quando mancano i canali e i ruoli citati nella configurazione di un server (tabella `config_orfani`, migrazione 0830).
Funzioni coperte: SPEC §20 (NF-05), catalogo #128 (UTL-226)
"""

from __future__ import annotations

from datetime import datetime

import asyncpg


class ConfigOrfaniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def elenco(self, guild_id: int) -> dict[tuple[str, int], datetime]:
        """`{(tipo, id): mancante_dal}` di un server."""
        righe = await self._pool.fetch(
            "SELECT tipo, oggetto_id, mancante_dal FROM config_orfani WHERE guild_id = $1", guild_id
        )
        return {(r["tipo"], r["oggetto_id"]): r["mancante_dal"] for r in righe}

    async def segna(self, guild_id: int, voci: list[tuple[str, int]], quando: datetime) -> None:
        """Segna la data solo per chi non ce l'ha già: la data più vecchia resta."""
        if not voci:
            return
        await self._pool.executemany(
            "INSERT INTO config_orfani (guild_id, tipo, oggetto_id, mancante_dal) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT DO NOTHING",
            [(guild_id, tipo, i, quando) for tipo, i in voci],
        )

    async def togli(self, guild_id: int, voci: list[tuple[str, int]]) -> None:
        """Toglie il segno (l'oggetto è tornato, o non è più citato, o la configurazione è stata pulita)."""
        if not voci:
            return
        await self._pool.executemany(
            "DELETE FROM config_orfani WHERE guild_id = $1 AND tipo = $2 AND oggetto_id = $3",
            [(guild_id, tipo, i) for tipo, i in voci],
        )


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


config_orfani_repo = ConfigOrfaniRepository(pool_provider=_get_pool)
