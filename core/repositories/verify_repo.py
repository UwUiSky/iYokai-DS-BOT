"""
core/repositories/verify_repo.py
===================================
Persistenza del Verify Base: configurazione per server, whitelist,
blacklist, log di ogni tentativo (SPEC.md §4.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class VerifyConfig:
    guild_id: int
    method: str  # "button" | "reaction"
    verified_role_id: int | None
    panel_channel_id: int | None
    panel_message_id: int | None
    log_channel_id: int | None
    min_account_age_days: int
    min_mutual_servers: int
    captcha_enabled: bool


DEFAULT_METHOD = "button"


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS verify_config (
            guild_id             BIGINT PRIMARY KEY,
            method               TEXT NOT NULL DEFAULT 'button',
            verified_role_id     BIGINT,
            panel_channel_id     BIGINT,
            panel_message_id     BIGINT,
            log_channel_id       BIGINT,
            min_account_age_days INTEGER NOT NULL DEFAULT 0,
            min_mutual_servers   INTEGER NOT NULL DEFAULT 0,
            captcha_enabled      BOOLEAN NOT NULL DEFAULT FALSE
        );

        CREATE TABLE IF NOT EXISTS verify_attempts (
            id           SERIAL PRIMARY KEY,
            guild_id     BIGINT NOT NULL,
            user_id      BIGINT NOT NULL,
            success      BOOLEAN NOT NULL,
            reason       TEXT NOT NULL,
            attempted_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_verify_attempts_guild_user
            ON verify_attempts (guild_id, user_id, attempted_at DESC);

        CREATE TABLE IF NOT EXISTS verify_whitelist (
            guild_id BIGINT NOT NULL,
            user_id  BIGINT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS verify_blacklist (
            guild_id BIGINT NOT NULL,
            user_id  BIGINT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        );
        """
    )


class VerifyRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ================================================================
    # Configurazione
    # ================================================================
    async def get_config(self, guild_id: int) -> VerifyConfig:
        row = await self._pool.fetchrow(
            "SELECT * FROM verify_config WHERE guild_id = $1", guild_id
        )
        if row is None:
            return VerifyConfig(
                guild_id=guild_id,
                method=DEFAULT_METHOD,
                verified_role_id=None,
                panel_channel_id=None,
                panel_message_id=None,
                log_channel_id=None,
                min_account_age_days=0,
                min_mutual_servers=0,
                captcha_enabled=False,
            )
        return VerifyConfig(
            guild_id=row["guild_id"],
            method=row["method"],
            verified_role_id=row["verified_role_id"],
            panel_channel_id=row["panel_channel_id"],
            panel_message_id=row["panel_message_id"],
            log_channel_id=row["log_channel_id"],
            min_account_age_days=row["min_account_age_days"],
            min_mutual_servers=row["min_mutual_servers"],
            captcha_enabled=row["captcha_enabled"],
        )

    async def set_config(
        self,
        guild_id: int,
        method: str,
        verified_role_id: int,
        min_account_age_days: int,
        min_mutual_servers: int,
        captcha_enabled: bool,
        log_channel_id: int | None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO verify_config
                (guild_id, method, verified_role_id, min_account_age_days,
                 min_mutual_servers, captcha_enabled, log_channel_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (guild_id) DO UPDATE
                SET method = EXCLUDED.method,
                    verified_role_id = EXCLUDED.verified_role_id,
                    min_account_age_days = EXCLUDED.min_account_age_days,
                    min_mutual_servers = EXCLUDED.min_mutual_servers,
                    captcha_enabled = EXCLUDED.captcha_enabled,
                    log_channel_id = EXCLUDED.log_channel_id
            """,
            guild_id,
            method,
            verified_role_id,
            min_account_age_days,
            min_mutual_servers,
            captcha_enabled,
            log_channel_id,
        )

    async def set_panel_message(
        self, guild_id: int, channel_id: int, message_id: int
    ) -> None:
        """
        Registra QUALE messaggio è il pannello di verify — necessario
        per la modalità reaction (bisogna sapere a quale messaggio
        ascoltare le reazioni) e utile anche in modalità button per
        diagnostica.
        """
        await self._pool.execute(
            """
            INSERT INTO verify_config (guild_id, panel_channel_id, panel_message_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET panel_channel_id = EXCLUDED.panel_channel_id,
                    panel_message_id = EXCLUDED.panel_message_id
            """,
            guild_id,
            channel_id,
            message_id,
        )

    # ================================================================
    # Whitelist / Blacklist
    # ================================================================
    async def is_whitelisted(self, guild_id: int, user_id: int) -> bool:
        row = await self._pool.fetchrow(
            "SELECT 1 FROM verify_whitelist WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )
        return row is not None

    async def add_whitelist(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO verify_whitelist (guild_id, user_id) VALUES ($1, $2)
            ON CONFLICT (guild_id, user_id) DO NOTHING
            """,
            guild_id,
            user_id,
        )

    async def remove_whitelist(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM verify_whitelist WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )

    async def is_blacklisted(self, guild_id: int, user_id: int) -> bool:
        row = await self._pool.fetchrow(
            "SELECT 1 FROM verify_blacklist WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )
        return row is not None

    async def add_blacklist(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO verify_blacklist (guild_id, user_id) VALUES ($1, $2)
            ON CONFLICT (guild_id, user_id) DO NOTHING
            """,
            guild_id,
            user_id,
        )

    async def remove_blacklist(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM verify_blacklist WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )

    # ================================================================
    # Log tentativi (SPEC.md §4.6)
    # ================================================================
    async def log_attempt(
        self, guild_id: int, user_id: int, success: bool, reason: str
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO verify_attempts (guild_id, user_id, success, reason)
            VALUES ($1, $2, $3, $4)
            """,
            guild_id,
            user_id,
            success,
            reason,
        )

    async def get_recent_attempts(
        self, guild_id: int, user_id: int, limit: int = 10
    ) -> list[tuple[bool, str, datetime]]:
        rows = await self._pool.fetch(
            """
            SELECT success, reason, attempted_at FROM verify_attempts
            WHERE guild_id = $1 AND user_id = $2
            ORDER BY attempted_at DESC LIMIT $3
            """,
            guild_id,
            user_id,
            limit,
        )
        return [(r["success"], r["reason"], r["attempted_at"]) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


verify_repo = VerifyRepository(pool_provider=_get_pool)
