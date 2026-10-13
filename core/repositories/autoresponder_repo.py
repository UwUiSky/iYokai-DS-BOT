"""
core/repositories/autoresponder_repo.py
=======================================
Risposte automatiche del server (NF-10). Tabella:
core/migrations/0083_autoresponder.sql.
Funzioni coperte: SPEC §14.7 (NF-10)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.autoresponder_logic import MAX_RISPOSTE


@dataclass(frozen=True)
class Autoresponder:
    id: int
    guild_id: int
    trigger: str
    match_mode: str
    response: str
    channel_id: int | None
    role_id: int | None
    ping_ruoli: bool


_COLONNE = "id, guild_id, trigger, match_mode, response, channel_id, role_id, ping_ruoli"


class AutoresponderRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def create(
        self,
        guild_id: int,
        trigger: str,
        *,
        match_mode: str,
        response: str,
        channel_id: int | None,
        role_id: int | None,
        ping_ruoli: bool,
        created_by: int,
    ) -> tuple[str, int | None]:
        """("ok", id), ("esiste", None) o ("pieno", None). Tetto e scrittura nella stessa query."""
        riga = await self._pool.fetchrow(
            """
            INSERT INTO autoresponders
                (guild_id, trigger, match_mode, response, channel_id, role_id, ping_ruoli, created_by)
            SELECT $1, $2, $3, $4, $5, $6, $7, $8
            WHERE (SELECT count(*) FROM autoresponders WHERE guild_id = $1) < $9
            ON CONFLICT (guild_id, lower(trigger)) DO NOTHING
            RETURNING id
            """,
            guild_id, trigger, match_mode, response, channel_id, role_id, ping_ruoli, created_by, MAX_RISPOSTE,
        )
        if riga is not None:
            return "ok", riga["id"]
        esiste = await self._pool.fetchval(
            "SELECT 1 FROM autoresponders WHERE guild_id = $1 AND lower(trigger) = lower($2)", guild_id, trigger
        )
        return ("esiste" if esiste else "pieno"), None

    async def list(self, guild_id: int) -> list[Autoresponder]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM autoresponders WHERE guild_id = $1 ORDER BY id", guild_id
        )
        return [Autoresponder(**dict(r)) for r in righe]

    async def delete(self, guild_id: int, responder_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM autoresponders WHERE guild_id = $1 AND id = $2", guild_id, responder_id
        )
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db
    return db.pool


autoresponder_repo = AutoresponderRepository(pool_provider=_get_pool)
