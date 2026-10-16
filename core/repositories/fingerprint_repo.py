"""
core/repositories/fingerprint_repo.py
=====================================
Impronte della verifica web e doppi trovati (tabelle `verify_impronte` e
`verify_doppi`, migrazione 0210). Solo impronte HMAC, mai IP in chiaro.
Le righe vecchie le toglie il lavoro giornaliero (`core/data_registry.py`).
Funzioni coperte: SPEC §4.2, §4.3 (NF-21)
"""

from __future__ import annotations

import asyncpg

MAX_ELENCO = 25


class FingerprintRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def registra(self, guild_id: int, user_id: int, impronte: dict[str, str]) -> list[tuple[int, str]]:
        """
        Salva (o rinnova) le impronte del membro e restituisce chi, nello stesso
        server, ne ha una uguale: [(altro membro, tipo)]. Una sola transazione.
        """
        if not impronte:
            return []
        async with self._pool.acquire() as conn, conn.transaction():
            uguali = await conn.fetch(
                """
                SELECT user_id, tipo FROM verify_impronte
                WHERE guild_id = $1 AND user_id <> $2
                  AND (tipo, impronta) IN (SELECT * FROM unnest($3::text[], $4::text[]))
                """,
                guild_id, user_id, list(impronte), list(impronte.values()),
            )
            await conn.executemany(
                """
                INSERT INTO verify_impronte (guild_id, user_id, tipo, impronta) VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, user_id, tipo)
                DO UPDATE SET impronta = EXCLUDED.impronta, creato_il = now()
                """,
                [(guild_id, user_id, tipo, valore) for tipo, valore in impronte.items()],
            )
        return [(r["user_id"], r["tipo"]) for r in uguali]

    async def salva_doppi(self, guild_id: int, user_id: int, doppi: list[tuple[int, str]]) -> None:
        """`doppi`: (altro membro, livello). Una coppia già vista si aggiorna."""
        if not doppi:
            return
        await self._pool.executemany(
            """
            INSERT INTO verify_doppi (guild_id, user_id, altro_user_id, livello) VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id, altro_user_id)
            DO UPDATE SET livello = EXCLUDED.livello, trovato_il = now()
            """,
            [(guild_id, user_id, altro, livello) for altro, livello in doppi],
        )

    async def elenco_doppi(self, guild_id: int, limite: int = MAX_ELENCO) -> list[asyncpg.Record]:
        """I doppi più recenti del server (al massimo 25)."""
        return await self._pool.fetch(
            """
            SELECT user_id, altro_user_id, livello, trovato_il FROM verify_doppi
            WHERE guild_id = $1 ORDER BY trovato_il DESC LIMIT $2
            """,
            guild_id, min(limite, MAX_ELENCO),
        )


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


fingerprint_repo = FingerprintRepository(pool_provider=_get_pool)
