"""
core/repositories/escalation_repo.py
=======================================
Persistenza della Smart AutoMod Escalation Ladder: conteggio
infrazioni per utente (con reset dopo buona condotta) e la scala di
azioni configurata per server.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.escalation_ladder_logic import LadderStep

# Scala di default, usata finché l'admin non ne configura una
# propria — ragionevole punto di partenza, non arbitraria: warn poi
# due timeout crescenti, senza azioni distruttive (kick/ban) di
# default. Un admin che vuole di più la configura esplicitamente.
DEFAULT_LADDER: list[LadderStep] = [
    LadderStep(level=1, action_type="warn"),
    LadderStep(level=2, action_type="timeout", duration_seconds=600),   # 10 minuti
    LadderStep(level=3, action_type="timeout", duration_seconds=3600),  # 1 ora
]
DEFAULT_RESET_AFTER_DAYS = 30


@dataclass(frozen=True)
class EscalationConfig:
    guild_id: int
    enabled: bool
    reset_after_days: int
    ladder: list[LadderStep]


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS automod_violations (
            guild_id           BIGINT NOT NULL,
            user_id            BIGINT NOT NULL,
            violation_count    INTEGER NOT NULL DEFAULT 0,
            last_violation_at  TIMESTAMPTZ,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS automod_escalation_config (
            guild_id          BIGINT PRIMARY KEY,
            enabled           BOOLEAN NOT NULL DEFAULT FALSE,
            reset_after_days  INTEGER NOT NULL DEFAULT 30
        );

        CREATE TABLE IF NOT EXISTS automod_escalation_steps (
            id                SERIAL PRIMARY KEY,
            guild_id          BIGINT NOT NULL,
            level             INTEGER NOT NULL,
            action_type       TEXT NOT NULL,
            duration_seconds  INTEGER,
            UNIQUE (guild_id, level)
        );
        """
    )


class EscalationRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ================================================================
    # Configurazione
    # ================================================================
    async def get_config(self, guild_id: int) -> EscalationConfig:
        row = await self._pool.fetchrow(
            "SELECT enabled, reset_after_days FROM automod_escalation_config WHERE guild_id = $1",
            guild_id,
        )
        enabled = row["enabled"] if row else False
        reset_after_days = row["reset_after_days"] if row else DEFAULT_RESET_AFTER_DAYS

        step_rows = await self._pool.fetch(
            "SELECT level, action_type, duration_seconds FROM automod_escalation_steps "
            "WHERE guild_id = $1 ORDER BY level",
            guild_id,
        )
        if step_rows:
            ladder = [
                LadderStep(r["level"], r["action_type"], r["duration_seconds"])
                for r in step_rows
            ]
        else:
            # Nessuna scala configurata esplicitamente: quella di
            # default, non una scala vuota — un admin che attiva il
            # modulo senza configurare nulla deve avere comunque un
            # comportamento sensato, non "escalation attiva ma senza
            # nessuna azione".
            ladder = DEFAULT_LADDER

        return EscalationConfig(guild_id, enabled, reset_after_days, ladder)

    async def set_enabled(self, guild_id: int, enabled: bool) -> None:
        await self._pool.execute(
            """
            INSERT INTO automod_escalation_config (guild_id, enabled)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET enabled = EXCLUDED.enabled
            """,
            guild_id,
            enabled,
        )

    async def set_reset_after_days(self, guild_id: int, days: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO automod_escalation_config (guild_id, reset_after_days)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET reset_after_days = EXCLUDED.reset_after_days
            """,
            guild_id,
            days,
        )

    async def set_step(
        self, guild_id: int, level: int, action_type: str, duration_seconds: int | None
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO automod_escalation_steps (guild_id, level, action_type, duration_seconds)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, level) DO UPDATE
                SET action_type = EXCLUDED.action_type,
                    duration_seconds = EXCLUDED.duration_seconds
            """,
            guild_id,
            level,
            action_type,
            duration_seconds,
        )

    async def remove_step(self, guild_id: int, level: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM automod_escalation_steps WHERE guild_id = $1 AND level = $2",
            guild_id,
            level,
        )
        return result.endswith(" 1")

    # ================================================================
    # Conteggio infrazioni
    # ================================================================
    async def get_violation_state(
        self, guild_id: int, user_id: int
    ) -> tuple[int, datetime | None]:
        row = await self._pool.fetchrow(
            "SELECT violation_count, last_violation_at FROM automod_violations "
            "WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )
        if row is None:
            return 0, None
        return row["violation_count"], row["last_violation_at"]

    async def record_violation(
        self, guild_id: int, user_id: int, new_count: int, when: datetime
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO automod_violations (guild_id, user_id, violation_count, last_violation_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET violation_count = EXCLUDED.violation_count,
                    last_violation_at = EXCLUDED.last_violation_at
            """,
            guild_id,
            user_id,
            new_count,
            when,
        )

    async def reset_violations(self, guild_id: int, user_id: int) -> None:
        """Azzeramento manuale (es. comando admin '/automod escalation reset')."""
        await self._pool.execute(
            "DELETE FROM automod_violations WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )


def _get_pool():
    from core.database import db
    return db.pool


escalation_repo = EscalationRepository(pool_provider=_get_pool)
