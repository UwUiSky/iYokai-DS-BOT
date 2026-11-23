"""
core/repositories/livelli_import_repo.py
========================================
Scrive in una transazione sola gli XP letti da un file esportato dall'admin. Non toglie mai XP a nessuno
(`ON CONFLICT ... WHERE EXCLUDED.xp_total > t.xp_total`), quindi lo stesso file si può caricare due volte senza
effetti in più; il livello si calcola con la formula e il tetto del server. Un solo import alla volta per server.
Funzioni coperte: LIV-072
"""

from __future__ import annotations

import asyncpg

from core.leveling_logic import level_for_xp
from core.livelli_import_logic import RigaImport


class LivelliImportRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def importa(self, guild_id: int, righe: list[RigaImport], *, tetto_livello: int = 0, formula: str = "classica") -> tuple[int, int]:
        """Restituisce (persone nuove o aumentate, persone lasciate come erano)."""
        ids = [r.user_id for r in righe]
        xp = [r.xp for r in righe]
        livelli = [level_for_xp(r.xp, tetto_livello, formula) for r in righe]
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext('livelli_import'), hashtext($1::text))", str(guild_id))
                cambiate = await conn.fetchval(
                    "WITH r AS (INSERT INTO leveling_totals AS t (guild_id, user_id, xp_total, level) "
                    "SELECT $1, u, x, l FROM unnest($2::bigint[], $3::bigint[], $4::int[]) AS d(u, x, l) "
                    "ON CONFLICT (guild_id, user_id) DO UPDATE SET xp_total = EXCLUDED.xp_total, level = EXCLUDED.level "
                    "WHERE EXCLUDED.xp_total > t.xp_total RETURNING 1) SELECT count(*) FROM r",
                    guild_id, ids, xp, livelli,
                )
        return cambiate, len(righe) - cambiate


def _get_pool():
    from core.database import db

    return db.pool


livelli_import_repo = LivelliImportRepository(pool_provider=_get_pool)
