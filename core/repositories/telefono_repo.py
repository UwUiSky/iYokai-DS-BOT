"""
core/repositories/telefono_repo.py
==================================
Il telefono tra server: canale di ogni server, blocchi (utenti e server) e registro delle chiamate (solo server,
ora e durata). Tabelle: core/migrations/0579_telefono.sql, 0580_telefono_registro.sql.
Funzioni coperte: SPEC §16 (FUN-079)
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

TIPO_UTENTE = "utente"
TIPO_SERVER = "server"


class TelefonoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # --- canale e webhook ---
    async def imposta_canale(self, guild_id: int, canale_id: int) -> None:
        await self._pool.execute(
            "INSERT INTO telefono_server (guild_id, canale_id) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET canale_id = EXCLUDED.canale_id, aggiornato_il = now()",
            guild_id, canale_id,
        )

    async def canale(self, guild_id: int) -> int | None:
        return await self._pool.fetchval("SELECT canale_id FROM telefono_server WHERE guild_id = $1", guild_id)

    async def canali(self) -> dict[int, int]:
        righe = await self._pool.fetch("SELECT guild_id, canale_id FROM telefono_server")
        return {r["guild_id"]: r["canale_id"] for r in righe}

    async def segna_webhook(self, guild_id: int, webhook_id: int | None) -> None:
        await self._pool.execute(
            "UPDATE telefono_server SET webhook_id = $2 WHERE guild_id = $1", guild_id, webhook_id
        )

    async def webhook_rimasti(self) -> list[tuple[int, int]]:
        """(server, webhook) delle chiamate rimaste aperte da prima del riavvio."""
        righe = await self._pool.fetch("SELECT guild_id, webhook_id FROM telefono_server WHERE webhook_id IS NOT NULL")
        return [(r["guild_id"], r["webhook_id"]) for r in righe]

    # --- blocchi ---
    async def blocca(self, guild_id: int, tipo: str, bersaglio_id: int) -> bool:
        """True se il blocco è nuovo."""
        esito = await self._pool.execute(
            "INSERT INTO telefono_blocchi (guild_id, tipo, bersaglio_id) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            guild_id, tipo, bersaglio_id,
        )
        return esito.endswith("1")

    async def sblocca(self, guild_id: int, tipo: str, bersaglio_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM telefono_blocchi WHERE guild_id = $1 AND tipo = $2 AND bersaglio_id = $3",
            guild_id, tipo, bersaglio_id,
        )
        return esito.endswith("1")

    async def bloccato(self, guild_id: int, tipo: str, bersaglio_id: int) -> bool:
        return bool(await self._pool.fetchval(
            "SELECT 1 FROM telefono_blocchi WHERE guild_id = $1 AND tipo = $2 AND bersaglio_id = $3",
            guild_id, tipo, bersaglio_id,
        ))

    async def server_che_bloccano(self, guild_id: int) -> set[int]:
        """I server che hanno bloccato `guild_id`."""
        righe = await self._pool.fetch(
            "SELECT guild_id FROM telefono_blocchi WHERE tipo = 'server' AND bersaglio_id = $1", guild_id
        )
        return {r["guild_id"] for r in righe}

    async def elenco_blocchi(self, guild_id: int, limite: int = 25) -> list[tuple[str, int]]:
        righe = await self._pool.fetch(
            "SELECT tipo, bersaglio_id FROM telefono_blocchi WHERE guild_id = $1 ORDER BY creato_il DESC LIMIT $2",
            guild_id, limite,
        )
        return [(r["tipo"], r["bersaglio_id"]) for r in righe]

    # --- registro ---
    async def registra(self, guild_a: int, guild_b: int, iniziata_il: datetime, durata: int, fine: str, segnalata: bool) -> None:
        await self._pool.execute(
            "INSERT INTO telefono_registro (guild_a, guild_b, iniziata_il, durata_secondi, fine, segnalata) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            guild_a, guild_b, iniziata_il, max(0, durata), fine[:20], segnalata,
        )

    async def registro(self, guild_id: int, limite: int = 10) -> list[asyncpg.Record]:
        """Le ultime chiamate del server; l'altro server è in `altro`."""
        return await self._pool.fetch(
            "SELECT CASE WHEN guild_a = $1 THEN guild_b ELSE guild_a END AS altro, iniziata_il, durata_secondi, fine, segnalata "
            "FROM telefono_registro WHERE guild_a = $1 OR guild_b = $1 ORDER BY iniziata_il DESC LIMIT $2",
            guild_id, limite,
        )


def _get_pool():
    from core.database import db

    return db.pool


telefono_repo = TelefonoRepository(pool_provider=_get_pool)
