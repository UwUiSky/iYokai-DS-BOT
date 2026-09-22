"""
core/repositories/monthly_winners_repo.py
=============================================
Configurazione dell'annuncio automatico dei vincitori (SPEC.md
§15.11): un canale per server, più l'ultimo periodo già annunciato —
è questa colonna a rendere l'annuncio IDEMPOTENTE (uno solo per mese,
anche con riavvii del bot o più tick nella stessa giornata).
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class MonthlyWinnersConfig:
    guild_id: int
    channel_id: int
    last_announced_period: str | None


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_winners_config (
            guild_id               BIGINT PRIMARY KEY,
            channel_id             BIGINT NOT NULL,
            last_announced_period  TEXT
        );
        """
    )


class MonthlyWinnersRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_config(self, row) -> MonthlyWinnersConfig:
        return MonthlyWinnersConfig(
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            last_announced_period=row["last_announced_period"],
        )

    async def set_channel(
        self, guild_id: int, channel_id: int, already_covered_period: str
    ) -> None:
        """
        already_covered_period viene salvato come 'già annunciato' alla
        PRIMA configurazione: chi attiva l'annuncio il 15 settembre non
        riceve subito, dal nulla, i vincitori di agosto — il primo
        annuncio arriva al prossimo cambio mese, che è quello che ci si
        aspetta attivando una funzione "a fine mese". Se la riga esiste
        già (cambio canale), last_announced_period NON viene toccato.
        """
        await self._pool.execute(
            """
            INSERT INTO monthly_winners_config (guild_id, channel_id, last_announced_period)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id
            """,
            guild_id,
            channel_id,
            already_covered_period,
        )

    async def disable(self, guild_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM monthly_winners_config WHERE guild_id = $1", guild_id
        )
        return result.endswith(" 1")

    async def get_config(self, guild_id: int) -> MonthlyWinnersConfig | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM monthly_winners_config WHERE guild_id = $1", guild_id
        )
        return self._row_to_config(row) if row is not None else None

    async def get_all_configs(self) -> list[MonthlyWinnersConfig]:
        rows = await self._pool.fetch("SELECT * FROM monthly_winners_config")
        return [self._row_to_config(r) for r in rows]

    async def mark_announced(self, guild_id: int, period: str) -> None:
        await self._pool.execute(
            "UPDATE monthly_winners_config SET last_announced_period = $2 WHERE guild_id = $1",
            guild_id,
            period,
        )


def _get_pool():
    from core.database import db
    return db.pool


monthly_winners_repo = MonthlyWinnersRepository(pool_provider=_get_pool)
