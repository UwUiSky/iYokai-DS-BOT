"""
core/repositories/eval_shell_log_repo.py
============================================
Log persistente di ogni invocazione di eval/exec/shell (SPEC.md
§17.3). Append-only per lo stesso motivo di premium_toggle_history:
chi ha eseguito codice arbitrario sul bot, cosa ha eseguito e quando,
deve restare tracciabile per sempre, non solo l'ultimo utilizzo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class EvalShellLogEntry:
    id: int
    executor_id: int
    kind: str
    code_or_command: str
    success: bool
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_shell_log (
            id               SERIAL PRIMARY KEY,
            executor_id      BIGINT NOT NULL,
            kind             TEXT NOT NULL,
            code_or_command  TEXT NOT NULL,
            success          BOOLEAN NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_eval_shell_log_created
            ON eval_shell_log (created_at DESC);
        """
    )


class EvalShellLogRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def log(self, executor_id: int, kind: str, code_or_command: str, success: bool) -> None:
        await self._pool.execute(
            """
            INSERT INTO eval_shell_log (executor_id, kind, code_or_command, success)
            VALUES ($1, $2, $3, $4)
            """,
            executor_id,
            kind,
            code_or_command,
            success,
        )

    async def get_recent(self, limit: int = 25) -> list[EvalShellLogEntry]:
        rows = await self._pool.fetch(
            "SELECT * FROM eval_shell_log ORDER BY created_at DESC LIMIT $1", limit
        )
        return [
            EvalShellLogEntry(
                id=r["id"],
                executor_id=r["executor_id"],
                kind=r["kind"],
                code_or_command=r["code_or_command"],
                success=r["success"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


def _get_pool():
    from core.database import db
    return db.pool


eval_shell_log_repo = EvalShellLogRepository(pool_provider=_get_pool)
