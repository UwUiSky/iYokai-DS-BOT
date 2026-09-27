"""
core/repositories/automod_advanced_repo.py
==============================================
Persistenza dei filtri AutoMod avanzati lato bot (SPEC.md
§6.3-§6.14): anti-link, anti-spam (messaggi/emoji/sticker/allegati),
anti-caps, anti-zalgo, anti-mass-mention, le eccezioni per
canale/ruolo (§6.11/§6.12), le azioni configurabili per violazione
(§6.13) e il canale di log (§6.14, la riga di log persistente vive
invece in `automod_action_log` più sotto).

Un'unica riga JSONB per server (stesso pattern di `guild_config.
settings`): la configurazione ha troppi campi annidati per
giustificare una colonna dedicata per ciascuno, e cresce ancora se in
futuro si aggiungono altri filtri.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import asyncpg

from core.automod_advanced_logic import (
    AntiLinkConfig,
    AutomodAdvancedConfig,
    CapsFilterConfig,
    RateFilterConfig,
    ThresholdFilterConfig,
)

# Azioni valide per una violazione (SPEC.md §6.13). L'ordine qui è
# anche l'ordine di ESECUZIONE quando più azioni sono configurate
# insieme: "delete" va sempre prima (altrimenti mute/ban su un utente
# che se ne va per il ban lascerebbe comunque il messaggio incriminato
# visibile per una frazione di secondo in più del necessario).
VALID_ACTIONS = ("delete", "warn", "mute", "ban")

DEFAULT_MUTE_DURATION_SECONDS = 600  # 10 minuti — valore di default per inferenza, configurabile


@dataclass(frozen=True)
class AutomodAdvancedSettings:
    """Configurazione completa per un server: filtri + eccezioni + azioni + log."""

    guild_id: int
    config: AutomodAdvancedConfig
    exempt_channel_ids: tuple[int, ...]
    exempt_role_ids: tuple[int, ...]
    actions: dict  # {violation_key: tuple[str, ...]}
    mute_duration_seconds: int
    log_channel_id: int | None


def _default_settings(guild_id: int) -> AutomodAdvancedSettings:
    return AutomodAdvancedSettings(
        guild_id=guild_id,
        config=AutomodAdvancedConfig(),
        exempt_channel_ids=(),
        exempt_role_ids=(),
        actions={},
        mute_duration_seconds=DEFAULT_MUTE_DURATION_SECONDS,
        log_channel_id=None,
    )


def _to_json(settings: AutomodAdvancedSettings) -> str:
    config = settings.config
    return json.dumps(
        {
            "anti_link": {
                "mode": config.anti_link.mode,
                "whitelist": list(config.anti_link.whitelist),
                "blacklist": list(config.anti_link.blacklist),
            },
            "anti_spam_messages": {
                "enabled": config.anti_spam_messages.enabled,
                "max_count": config.anti_spam_messages.max_count,
                "window_seconds": config.anti_spam_messages.window_seconds,
            },
            "anti_spam_emoji": {
                "enabled": config.anti_spam_emoji.enabled,
                "max_count": config.anti_spam_emoji.max_count,
            },
            "anti_spam_sticker": {
                "enabled": config.anti_spam_sticker.enabled,
                "max_count": config.anti_spam_sticker.max_count,
                "window_seconds": config.anti_spam_sticker.window_seconds,
            },
            "anti_caps": {
                "enabled": config.anti_caps.enabled,
                "threshold_percent": config.anti_caps.threshold_percent,
                "min_length": config.anti_caps.min_length,
            },
            "anti_zalgo_enabled": config.anti_zalgo_enabled,
            "anti_mass_mention": {
                "enabled": config.anti_mass_mention.enabled,
                "max_count": config.anti_mass_mention.max_count,
            },
            "anti_attachment_spam": {
                "enabled": config.anti_attachment_spam.enabled,
                "max_count": config.anti_attachment_spam.max_count,
                "window_seconds": config.anti_attachment_spam.window_seconds,
            },
            "exempt_channel_ids": list(settings.exempt_channel_ids),
            "exempt_role_ids": list(settings.exempt_role_ids),
            "actions": {k: list(v) for k, v in settings.actions.items()},
            "mute_duration_seconds": settings.mute_duration_seconds,
            "log_channel_id": settings.log_channel_id,
        }
    )


def _from_json(guild_id: int, raw: str) -> AutomodAdvancedSettings:
    data = json.loads(raw)
    link = data.get("anti_link", {})
    spam_msg = data.get("anti_spam_messages", {})
    spam_emoji = data.get("anti_spam_emoji", {})
    spam_sticker = data.get("anti_spam_sticker", {})
    caps = data.get("anti_caps", {})
    mention = data.get("anti_mass_mention", {})
    attach = data.get("anti_attachment_spam", {})

    config = AutomodAdvancedConfig(
        anti_link=AntiLinkConfig(
            mode=link.get("mode", "off"),
            whitelist=tuple(link.get("whitelist", [])),
            blacklist=tuple(link.get("blacklist", [])),
        ),
        anti_spam_messages=RateFilterConfig(
            enabled=spam_msg.get("enabled", False),
            max_count=spam_msg.get("max_count", 5),
            window_seconds=spam_msg.get("window_seconds", 10),
        ),
        anti_spam_emoji=ThresholdFilterConfig(
            enabled=spam_emoji.get("enabled", False),
            max_count=spam_emoji.get("max_count", 5),
        ),
        anti_spam_sticker=RateFilterConfig(
            enabled=spam_sticker.get("enabled", False),
            max_count=spam_sticker.get("max_count", 3),
            window_seconds=spam_sticker.get("window_seconds", 30),
        ),
        anti_caps=CapsFilterConfig(
            enabled=caps.get("enabled", False),
            threshold_percent=caps.get("threshold_percent", 70),
            min_length=caps.get("min_length", 10),
        ),
        anti_zalgo_enabled=data.get("anti_zalgo_enabled", False),
        anti_mass_mention=ThresholdFilterConfig(
            enabled=mention.get("enabled", False),
            max_count=mention.get("max_count", 5),
        ),
        anti_attachment_spam=RateFilterConfig(
            enabled=attach.get("enabled", False),
            max_count=attach.get("max_count", 5),
            window_seconds=attach.get("window_seconds", 30),
        ),
    )

    return AutomodAdvancedSettings(
        guild_id=guild_id,
        config=config,
        exempt_channel_ids=tuple(data.get("exempt_channel_ids", [])),
        exempt_role_ids=tuple(data.get("exempt_role_ids", [])),
        actions={k: tuple(v) for k, v in data.get("actions", {}).items()},
        mute_duration_seconds=data.get("mute_duration_seconds", DEFAULT_MUTE_DURATION_SECONDS),
        log_channel_id=data.get("log_channel_id"),
    )


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS automod_advanced_config (
            guild_id   BIGINT PRIMARY KEY,
            settings   JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Log persistente delle azioni AutoMod avanzate (SPEC.md
        -- §6.14) — distinto dal log dei comandi di moderazione
        -- (moderation_cases): qui ogni riga è un evento AUTOMATICO,
        -- non un'azione decisa da un moderatore umano.
        CREATE TABLE IF NOT EXISTS automod_action_log (
            id          SERIAL PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            user_id     BIGINT NOT NULL,
            channel_id  BIGINT NOT NULL,
            violation   TEXT NOT NULL,
            actions_taken JSONB NOT NULL DEFAULT '[]'::jsonb,
            content_excerpt TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_automod_action_log_guild
            ON automod_action_log (guild_id, created_at DESC);
        """
    )


class AutomodAdvancedRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_settings(self, guild_id: int) -> AutomodAdvancedSettings:
        row = await self._pool.fetchrow(
            "SELECT settings FROM automod_advanced_config WHERE guild_id = $1", guild_id
        )
        if row is None:
            return _default_settings(guild_id)
        return _from_json(guild_id, row["settings"])

    async def save_settings(self, settings: AutomodAdvancedSettings) -> None:
        await self._pool.execute(
            """
            INSERT INTO automod_advanced_config (guild_id, settings)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (guild_id) DO UPDATE
                SET settings = EXCLUDED.settings, updated_at = now()
            """,
            settings.guild_id,
            _to_json(settings),
        )

    async def log_action(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int,
        violation: str,
        actions_taken: tuple[str, ...],
        content_excerpt: str | None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO automod_action_log
                (guild_id, user_id, channel_id, violation, actions_taken, content_excerpt)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            """,
            guild_id,
            user_id,
            channel_id,
            violation,
            json.dumps(list(actions_taken)),
            content_excerpt,
        )

    async def get_recent_actions(self, guild_id: int, limit: int = 20) -> list[dict]:
        """Usato da `/automod log-recenti` per mostrare l'ultimo storico senza uscire da Discord."""
        rows = await self._pool.fetch(
            """
            SELECT user_id, channel_id, violation, actions_taken, content_excerpt, created_at
            FROM automod_action_log
            WHERE guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [
            {
                "user_id": r["user_id"],
                "channel_id": r["channel_id"],
                "violation": r["violation"],
                "actions_taken": tuple(json.loads(r["actions_taken"])),
                "content_excerpt": r["content_excerpt"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


def _get_pool():
    from core.database import db
    return db.pool


automod_advanced_repo = AutomodAdvancedRepository(pool_provider=_get_pool)
