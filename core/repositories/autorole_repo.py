"""
core/repositories/autorole_repo.py
==================================
Ruoli automatici (con condizioni e "ridai se tolto") e ruoli ricordati di
chi esce (NF-07, SPEC §22; catalogo #123). Tabelle:
core/migrations/0080_autoroles.sql, 0230_autorole_condizioni.sql.
Funzioni coperte: SPEC §22 (NF-07)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.repositories.tetto_server import tetto_per_server

from core.autorole_logic import (
    GIORNI_MEMORIA_PREDEFINITI,
    MAX_REGOLE,
    RegolaAutoruolo,
)


@dataclass(frozen=True)
class AutoroleConfig:
    guild_id: int
    remember_enabled: bool
    remember_days: int


@dataclass(frozen=True)
class MemoriaRuoli:
    role_ids: list[int]
    left_at: datetime


class AutoroleRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def add_rule(
        self,
        guild_id: int,
        role_id: int,
        delay_seconds: int,
        created_by: int,
        *,
        richiesti: list[int] | None = None,
        esclusi: list[int] | None = None,
        ridai: bool = False,
    ) -> bool:
        """
        Aggiunge (o aggiorna) una regola. False se il server ha già
        MAX_REGOLE regole e questo ruolo è nuovo. Controllo e scrittura in un'unica query.
        """
        async with tetto_per_server(self._pool, "autorole_rules", guild_id) as conn:
            riga = await conn.fetchrow(
                """
                INSERT INTO autorole_rules
                    (guild_id, role_id, delay_seconds, created_by, required_role_ids, excluded_role_ids, reapply)
                SELECT $1, $2, $3, $4, $6, $7, $8
                WHERE EXISTS (SELECT 1 FROM autorole_rules WHERE guild_id = $1 AND role_id = $2)
                   OR (SELECT count(*) FROM autorole_rules WHERE guild_id = $1) < $5
                ON CONFLICT (guild_id, role_id) DO UPDATE SET
                    delay_seconds = EXCLUDED.delay_seconds,
                    required_role_ids = EXCLUDED.required_role_ids,
                    excluded_role_ids = EXCLUDED.excluded_role_ids,
                    reapply = EXCLUDED.reapply
                RETURNING role_id
                """,
                guild_id, role_id, delay_seconds, created_by, MAX_REGOLE,
                list(richiesti or []), list(esclusi or []), ridai,
            )
            return riga is not None

    async def remove_rule(self, guild_id: int, role_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM autorole_rules WHERE guild_id = $1 AND role_id = $2", guild_id, role_id
        )
        return esito.endswith(" 1")

    async def list_rules(self, guild_id: int) -> list[RegolaAutoruolo]:
        righe = await self._pool.fetch(
            """
            SELECT role_id, delay_seconds, required_role_ids, excluded_role_ids, reapply
            FROM autorole_rules WHERE guild_id = $1 ORDER BY created_at, role_id
            """,
            guild_id,
        )
        return [
            RegolaAutoruolo(
                r["role_id"], r["delay_seconds"], tuple(r["required_role_ids"]), tuple(r["excluded_role_ids"]), r["reapply"]
            )
            for r in righe
        ]

    async def get_config(self, guild_id: int) -> AutoroleConfig:
        riga = await self._pool.fetchrow(
            "SELECT remember_enabled, remember_days FROM autorole_config WHERE guild_id = $1", guild_id
        )
        if riga is None:
            return AutoroleConfig(guild_id, False, GIORNI_MEMORIA_PREDEFINITI)
        return AutoroleConfig(guild_id, riga["remember_enabled"], riga["remember_days"])

    async def set_remember(self, guild_id: int, enabled: bool, days: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO autorole_config (guild_id, remember_enabled, remember_days)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET remember_enabled = EXCLUDED.remember_enabled, remember_days = EXCLUDED.remember_days
            """,
            guild_id, enabled, days,
        )
        if not enabled:
            # Spento: i ruoli già ricordati non servono più, e sono dati personali.
            await self._pool.execute("DELETE FROM autorole_memory WHERE guild_id = $1", guild_id)

    async def save_memory(self, guild_id: int, user_id: int, role_ids: list[int], left_at: datetime) -> None:
        await self._pool.execute(
            """
            INSERT INTO autorole_memory (guild_id, user_id, role_ids, left_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET role_ids = EXCLUDED.role_ids, left_at = EXCLUDED.left_at
            """,
            guild_id, user_id, role_ids, left_at,
        )

    async def pop_memory(self, guild_id: int, user_id: int) -> MemoriaRuoli | None:
        """Legge e cancella in un colpo: i ruoli si ridanno una volta sola."""
        riga = await self._pool.fetchrow(
            "DELETE FROM autorole_memory WHERE guild_id = $1 AND user_id = $2 RETURNING role_ids, left_at",
            guild_id, user_id,
        )
        if riga is None:
            return None
        return MemoriaRuoli(list(riga["role_ids"]), riga["left_at"])


def _get_pool():
    from core.database import db
    return db.pool


autorole_repo = AutoroleRepository(pool_provider=_get_pool)
