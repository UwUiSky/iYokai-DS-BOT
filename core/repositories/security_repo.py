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

from core.security_logic import AntiNukeConfig, AntiRaidConfig, TrustEntry


# Quanti casi anti-nuke si tengono per server: i piu' vecchi si tolgono
# quando ne arriva uno nuovo (regola di pulizia della tabella, LIMITI.md
# Parte 4, punto 19).
MAX_CASI_NUKE_PER_SERVER = 500


@dataclass(frozen=True)
class NukeCase:
    """Un attacco fermato dall'anti-nuke (SIC-017)."""

    guild_id: int
    case_number: int
    actor_id: int | None
    category: str
    detail: str | None
    punishment: str | None
    removed_role_ids: tuple[int, ...]
    created_at: datetime
    released_at: datetime | None


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
                "quarantine_hold": r.quarantine_hold,
                "azione_eta": r.azione_eta,
                "azione_bot_non_verificato": r.azione_bot_non_verificato,
                "azione_nome_pubblicitario": r.azione_nome_pubblicitario,
                "azione_nome_vietato": r.azione_nome_vietato,
                "messaggio_eta": r.messaggio_eta,
                "nomi_vietati": list(r.nomi_vietati),
                "conta_solo_sospetti": r.conta_solo_sospetti,
                "account_vicini_minimo": r.account_vicini_minimo,
                "account_vicini_margine_secondi": r.account_vicini_margine_secondi,
                "nomi_simili_minimo": r.nomi_simili_minimo,
                "retroattivo": r.retroattivo,
                "ruoli_ping": list(r.ruoli_ping),
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
                "channel_perms_max": n.channel_perms_max,
                "channel_perms_window_seconds": n.channel_perms_window_seconds,
                "channel_hour_max": n.channel_hour_max,
                "role_hour_max": n.role_hour_max,
                "webhook_hour_max": n.webhook_hour_max,
                "emoji_hour_max": n.emoji_hour_max,
                "ban_kick_hour_max": n.ban_kick_hour_max,
                "channel_perms_hour_max": n.channel_perms_hour_max,
                "trusted_ids": list(n.trusted_ids),
                "punish_action": n.punish_action,
                "recovery_enabled": n.recovery_enabled,
                "trust_entries": [
                    {
                        "target_id": t.target_id,
                        "kind": t.kind,
                        "level": t.level,
                        "categories": list(t.categories),
                        "channel_category_id": t.channel_category_id,
                    }
                    for t in n.trust_entries
                ],
                "role_perm_guard": n.role_perm_guard,
                "member_role_guard": n.member_role_guard,
                "vanity_guard": n.vanity_guard,
                "bot_add_guard": n.bot_add_guard,
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
        quarantine_hold=r.get("quarantine_hold", False),
        azione_eta=r.get("azione_eta", "niente"),
        azione_bot_non_verificato=r.get("azione_bot_non_verificato", "niente"),
        azione_nome_pubblicitario=r.get("azione_nome_pubblicitario", "niente"),
        azione_nome_vietato=r.get("azione_nome_vietato", "niente"),
        messaggio_eta=r.get("messaggio_eta", ""),
        nomi_vietati=tuple(r.get("nomi_vietati", ())),
        conta_solo_sospetti=r.get("conta_solo_sospetti", False),
        account_vicini_minimo=r.get("account_vicini_minimo", 0),
        account_vicini_margine_secondi=r.get("account_vicini_margine_secondi", 3600),
        nomi_simili_minimo=r.get("nomi_simili_minimo", 0),
        retroattivo=r.get("retroattivo", False),
        ruoli_ping=tuple(r.get("ruoli_ping", ())),
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
        channel_perms_max=n.get("channel_perms_max", 5),
        channel_perms_window_seconds=n.get("channel_perms_window_seconds", 60),
        channel_hour_max=n.get("channel_hour_max", 10),
        role_hour_max=n.get("role_hour_max", 10),
        webhook_hour_max=n.get("webhook_hour_max", 10),
        emoji_hour_max=n.get("emoji_hour_max", 20),
        ban_kick_hour_max=n.get("ban_kick_hour_max", 10),
        channel_perms_hour_max=n.get("channel_perms_hour_max", 20),
        trusted_ids=tuple(n.get("trusted_ids", [])),
        # Una riga vecchia che non dice la punizione resta com'era: toglie i ruoli.
        punish_action=n.get("punish_action", "strip_roles"),
        recovery_enabled=n.get("recovery_enabled", True),
        trust_entries=tuple(
            TrustEntry(
                target_id=t["target_id"],
                kind=t.get("kind", "user"),
                level=t.get("level", "trusted"),
                categories=tuple(t.get("categories", [])),
                channel_category_id=t.get("channel_category_id"),
            )
            for t in n.get("trust_entries", [])
        ),
        role_perm_guard=n.get("role_perm_guard", "off"),
        member_role_guard=n.get("member_role_guard", False),
        vanity_guard=n.get("vanity_guard", False),
        bot_add_guard=n.get("bot_add_guard", False),
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

        -- Registro degli attacchi fermati dall'anti-nuke (SIC-017): un
        -- numero per server, i ruoli tolti all'autore (per rilasciarlo)
        -- e l'esito della punizione. Si tengono gli ultimi 500 per server.
        CREATE TABLE IF NOT EXISTS nuke_cases (
            guild_id         BIGINT NOT NULL,
            case_number      INTEGER NOT NULL,
            actor_id         BIGINT,
            category         TEXT NOT NULL,
            detail           TEXT,
            punishment       TEXT,
            removed_role_ids BIGINT[] NOT NULL DEFAULT '{}',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            released_at      TIMESTAMPTZ,
            PRIMARY KEY (guild_id, case_number)
        );

        CREATE INDEX IF NOT EXISTS idx_nuke_cases_attivi
            ON nuke_cases (guild_id, actor_id) WHERE released_at IS NULL;

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

    async def raid_joins(self, guild_id: int, dal: datetime, limite: int = 5000) -> list[dict]:
        """Gli ingressi di raid registrati da `dal` in poi, dal più vecchio (SIC-035)."""
        rows = await self._pool.fetch(
            """
            SELECT actor_id, detail, created_at FROM security_action_log
            WHERE guild_id = $1 AND category = 'raid_join' AND created_at >= $2
            ORDER BY created_at ASC LIMIT $3
            """,
            guild_id,
            dal,
            limite,
        )
        return [dict(r) for r in rows]

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
    # Registro degli attacchi (SIC-017)
    # ================================================================
    async def create_nuke_case(
        self,
        guild_id: int,
        actor_id: int | None,
        category: str,
        detail: str | None,
        punishment: str | None,
        removed_role_ids: tuple[int, ...] = (),
    ) -> int:
        """Salva un caso col numero successivo del server e lo restituisce."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Un blocco per server: due attacchi insieme non prendono lo stesso numero.
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                numero = await conn.fetchval(
                    "SELECT COALESCE(MAX(case_number), 0) + 1 FROM nuke_cases WHERE guild_id = $1",
                    guild_id,
                )
                await conn.execute(
                    """
                    INSERT INTO nuke_cases
                        (guild_id, case_number, actor_id, category, detail, punishment, removed_role_ids)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    guild_id, numero, actor_id, category, (detail or "")[:1000],
                    (punishment or "")[:300], list(removed_role_ids),
                )
                await conn.execute(
                    "DELETE FROM nuke_cases WHERE guild_id = $1 AND case_number <= $2",
                    guild_id, numero - MAX_CASI_NUKE_PER_SERVER,
                )
        return numero

    @staticmethod
    def _row_to_case(r) -> NukeCase:
        return NukeCase(
            guild_id=r["guild_id"],
            case_number=r["case_number"],
            actor_id=r["actor_id"],
            category=r["category"],
            detail=r["detail"],
            punishment=r["punishment"],
            removed_role_ids=tuple(r["removed_role_ids"] or ()),
            created_at=r["created_at"],
            released_at=r["released_at"],
        )

    async def get_nuke_case(self, guild_id: int, case_number: int) -> NukeCase | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM nuke_cases WHERE guild_id = $1 AND case_number = $2",
            guild_id, case_number,
        )
        return self._row_to_case(row) if row else None

    async def list_nuke_cases(
        self, guild_id: int, page: int = 1, per_page: int = 10
    ) -> tuple[list[NukeCase], int]:
        """Una pagina di casi (dal piu' recente) e il totale."""
        totale = await self._pool.fetchval(
            "SELECT COUNT(*) FROM nuke_cases WHERE guild_id = $1", guild_id
        )
        rows = await self._pool.fetch(
            """
            SELECT * FROM nuke_cases WHERE guild_id = $1
            ORDER BY case_number DESC LIMIT $2 OFFSET $3
            """,
            guild_id, per_page, max(page - 1, 0) * per_page,
        )
        return [self._row_to_case(r) for r in rows], totale

    async def active_cases_for_actor(self, guild_id: int, actor_id: int) -> list[NukeCase]:
        """I casi non ancora rilasciati di questo utente, dal piu' recente."""
        rows = await self._pool.fetch(
            """
            SELECT * FROM nuke_cases
            WHERE guild_id = $1 AND actor_id = $2 AND released_at IS NULL
            ORDER BY case_number DESC
            """,
            guild_id, actor_id,
        )
        return [self._row_to_case(r) for r in rows]

    async def extend_nuke_case(
        self, guild_id: int, case_number: int, punishment: str, removed_role_ids: tuple[int, ...]
    ) -> None:
        """
        Stesso attacco, punizione ripetuta perche' la prima non teneva: il
        caso resta uno, con l'esito nuovo e i ruoli tolti in piu' (quelli
        gia' registrati restano).
        """
        await self._pool.execute(
            """
            UPDATE nuke_cases
            SET punishment = $3,
                removed_role_ids = ARRAY(SELECT DISTINCT unnest(removed_role_ids || $4::bigint[]))
            WHERE guild_id = $1 AND case_number = $2
            """,
            guild_id, case_number, punishment[:300], list(removed_role_ids),
        )

    async def mark_nuke_case_released(self, guild_id: int, case_number: int) -> bool:
        """Segna il caso come rilasciato. False se non esiste o lo era gia'."""
        esito = await self._pool.execute(
            """
            UPDATE nuke_cases SET released_at = now()
            WHERE guild_id = $1 AND case_number = $2 AND released_at IS NULL
            """,
            guild_id, case_number,
        )
        return esito.endswith(" 1")

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
