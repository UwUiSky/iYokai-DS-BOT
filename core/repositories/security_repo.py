"""
core/repositories/security_repo.py
======================================
Persistenza della Security Suite (SPEC.md §7.1 Anti-Raid, §7.2
Anti-Nuke): un'unica riga JSONB per server, stesso pattern di
core/repositories/automod_advanced_repo.py — troppi campi annidati
per giustificare una colonna dedicata per ciascuno.

Il ruolo di quarantena (§7.1) e il canale di alert (condiviso da
Anti-Raid e Anti-Nuke) vivono anche loro in questa riga: sono
configurazione, non stato "caldo" — a differenza delle finestre
mobili di conteggio (core/security_rate_tracker.py), che restano
deliberatamente in memoria.

Il blocco anti-raid in corso (livello di verifica di prima e scadenza)
sta in una tabella a parte, così sopravvive a un riavvio.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.security_logic import AntiNukeConfig, AntiRaidConfig


@dataclass(frozen=True)
class SecuritySettings:
    guild_id: int
    anti_raid: AntiRaidConfig
    anti_nuke: AntiNukeConfig
    quarantine_role_id: int | None
    alert_channel_id: int | None


def _default_settings(guild_id: int) -> SecuritySettings:
    return SecuritySettings(
        guild_id=guild_id,
        anti_raid=AntiRaidConfig(),
        anti_nuke=AntiNukeConfig(),
        quarantine_role_id=None,
        alert_channel_id=None,
    )


def _to_json(settings: SecuritySettings) -> str:
    r, n = settings.anti_raid, settings.anti_nuke
    return json.dumps(
        {
            "anti_raid": {
                "enabled": r.enabled,
                "join_rate_max": r.join_rate_max,
                "join_rate_window_seconds": r.join_rate_window_seconds,
                "min_account_age_seconds": r.min_account_age_seconds,
                "check_username_pattern": r.check_username_pattern,
                "check_avatar_pattern": r.check_avatar_pattern,
                "lockdown_action": r.lockdown_action,
            },
            "anti_nuke": {
                "enabled": n.enabled,
                "channel_max": n.channel_max,
                "channel_window_seconds": n.channel_window_seconds,
                "role_max": n.role_max,
                "role_window_seconds": n.role_window_seconds,
                "webhook_max": n.webhook_max,
                "webhook_window_seconds": n.webhook_window_seconds,
                "emoji_max": n.emoji_max,
                "emoji_window_seconds": n.emoji_window_seconds,
                "ban_kick_max": n.ban_kick_max,
                "ban_kick_window_seconds": n.ban_kick_window_seconds,
                "trusted_ids": list(n.trusted_ids),
                "punish_action": n.punish_action,
                "recovery_enabled": n.recovery_enabled,
            },
            "quarantine_role_id": settings.quarantine_role_id,
            "alert_channel_id": settings.alert_channel_id,
        }
    )


def _from_json(guild_id: int, raw: str) -> SecuritySettings:
    data = json.loads(raw)
    r = data.get("anti_raid", {})
    n = data.get("anti_nuke", {})

    anti_raid = AntiRaidConfig(
        enabled=r.get("enabled", False),
        join_rate_max=r.get("join_rate_max", 10),
        join_rate_window_seconds=r.get("join_rate_window_seconds", 60),
        min_account_age_seconds=r.get("min_account_age_seconds", 86400),
        check_username_pattern=r.get("check_username_pattern", True),
        check_avatar_pattern=r.get("check_avatar_pattern", True),
        lockdown_action=r.get("lockdown_action", "quarantine"),
    )
    anti_nuke = AntiNukeConfig(
        enabled=n.get("enabled", False),
        channel_max=n.get("channel_max", 3),
        channel_window_seconds=n.get("channel_window_seconds", 60),
        role_max=n.get("role_max", 3),
        role_window_seconds=n.get("role_window_seconds", 60),
        webhook_max=n.get("webhook_max", 3),
        webhook_window_seconds=n.get("webhook_window_seconds", 60),
        emoji_max=n.get("emoji_max", 5),
        emoji_window_seconds=n.get("emoji_window_seconds", 60),
        ban_kick_max=n.get("ban_kick_max", 3),
        ban_kick_window_seconds=n.get("ban_kick_window_seconds", 60),
        trusted_ids=tuple(n.get("trusted_ids", [])),
        punish_action=n.get("punish_action", "strip_roles"),
        recovery_enabled=n.get("recovery_enabled", True),
    )

    return SecuritySettings(
        guild_id=guild_id,
        anti_raid=anti_raid,
        anti_nuke=anti_nuke,
        quarantine_role_id=data.get("quarantine_role_id"),
        alert_channel_id=data.get("alert_channel_id"),
    )


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS security_config (
            guild_id   BIGINT PRIMARY KEY,
            settings   JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Log persistente di ogni intervento Anti-Raid/Anti-Nuke —
        -- distinto da moderation_cases (azioni decise da un
        -- moderatore umano) e da automod_action_log (filtri sui
        -- MESSAGGI): qui sono eventi di sicurezza sul SERVER stesso.
        CREATE TABLE IF NOT EXISTS security_action_log (
            id          SERIAL PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            category    TEXT NOT NULL,
            actor_id    BIGINT,
            detail      TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_security_action_log_guild
            ON security_action_log (guild_id, created_at DESC);

        -- Blocco anti-raid in corso: il livello di verifica che il
        -- server aveva prima e quando il blocco scade. Una riga per
        -- server, cancellata alla fine del blocco.
        CREATE TABLE IF NOT EXISTS anti_raid_lockdown (
            guild_id        BIGINT PRIMARY KEY,
            previous_level  TEXT NOT NULL,
            expires_at      TIMESTAMPTZ NOT NULL
        );
        """
    )


class SecurityRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_settings(self, guild_id: int) -> SecuritySettings:
        row = await self._pool.fetchrow(
            "SELECT settings FROM security_config WHERE guild_id = $1", guild_id
        )
        if row is None:
            return _default_settings(guild_id)
        return _from_json(guild_id, row["settings"])

    async def save_settings(self, settings: SecuritySettings) -> None:
        await self._pool.execute(
            """
            INSERT INTO security_config (guild_id, settings)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (guild_id) DO UPDATE
                SET settings = EXCLUDED.settings, updated_at = now()
            """,
            settings.guild_id,
            _to_json(settings),
        )

    async def log_action(
        self, guild_id: int, category: str, actor_id: int | None, detail: str | None
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO security_action_log (guild_id, category, actor_id, detail)
            VALUES ($1, $2, $3, $4)
            """,
            guild_id,
            category,
            actor_id,
            detail,
        )

    async def get_recent_actions(self, guild_id: int, limit: int = 20) -> list[dict]:
        rows = await self._pool.fetch(
            """
            SELECT category, actor_id, detail, created_at
            FROM security_action_log
            WHERE guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [
            {
                "category": r["category"],
                "actor_id": r["actor_id"],
                "detail": r["detail"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


    # ================================================================
    # Blocco anti-raid (livello di verifica alzato per un tempo)
    # ================================================================
    async def start_or_extend_lockdown(
        self, guild_id: int, previous_level: str, expires_at: datetime
    ) -> None:
        """
        Apre il blocco o, se è già aperto, ne sposta solo la scadenza:
        il livello "di prima" resta quello salvato all'apertura.
        """
        await self._pool.execute(
            """
            INSERT INTO anti_raid_lockdown (guild_id, previous_level, expires_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET expires_at = EXCLUDED.expires_at
            """,
            guild_id,
            previous_level,
            expires_at,
        )

    async def get_expired_lockdowns(self, now: datetime) -> list[tuple[int, str]]:
        """I blocchi scaduti, come coppie (server, livello di prima)."""
        rows = await self._pool.fetch(
            "SELECT guild_id, previous_level FROM anti_raid_lockdown WHERE expires_at <= $1",
            now,
        )
        return [(r["guild_id"], r["previous_level"]) for r in rows]

    async def end_lockdown(self, guild_id: int) -> None:
        await self._pool.execute("DELETE FROM anti_raid_lockdown WHERE guild_id = $1", guild_id)


def _get_pool():
    from core.database import db
    return db.pool


security_repo = SecurityRepository(pool_provider=_get_pool)
