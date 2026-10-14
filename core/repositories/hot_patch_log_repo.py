"""
core/repositories/hot_patch_log_repo.py
=======================================
Registro degli aggiornamenti a caldo (tabella `hot_patch_log`, migrazione 0134, #141).
Funzioni coperte: SPEC §17.11
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class VoceRegistro:
    id: int
    applied_by: int
    source: str
    commit_sha: str | None
    files: list[str]
    outcome: str
    restart_needed: bool
    detail: str | None
    created_at: datetime


class HotPatchLogRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def registra(
        self,
        applied_by: int,
        source: str,
        commit_sha: str | None,
        files: list[str],
        outcome: str,
        restart_needed: bool,
        detail: str | None = None,
    ) -> int:
        return await self._pool.fetchval(
            """
            INSERT INTO hot_patch_log (applied_by, source, commit_sha, files, outcome, restart_needed, detail)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7) RETURNING id
            """,
            applied_by, source, commit_sha, json.dumps(files), outcome, restart_needed, detail and detail[:500],
        )

    async def ultimi(self, quanti: int = 10) -> list[VoceRegistro]:
        righe = await self._pool.fetch("SELECT * FROM hot_patch_log ORDER BY id DESC LIMIT $1", quanti)
        return [
            VoceRegistro(
                r["id"], r["applied_by"], r["source"], r["commit_sha"], json.loads(r["files"]),
                r["outcome"], r["restart_needed"], r["detail"], r["created_at"],
            )
            for r in righe
        ]


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


hot_patch_log_repo = HotPatchLogRepository(pool_provider=_get_pool)
