"""
core/repositories/activity_stats_repo.py
========================================
Conteggi giornalieri di attività (NF-25). Tabelle: core/migrations/0120_activity_stats.sql.
Solo aggregati per giorno; la pulizia a 90 giorni sta in core/data_registry.py.
Funzioni coperte: SPEC §23 (NF-25)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import asyncpg

from core.activity_stats_logic import MAX_REGOLE_PER_SERVER

_COLONNA = {"messages": "messages", "voice_minutes": "voice_seconds"}


def _somma(metrica: str) -> str:
    """Espressione SQL della somma della metrica: i minuti si ricavano dalla somma dei secondi
    (dividere ogni giorno per 60 prima di sommare perderebbe fino a 59 secondi al giorno)."""
    return "sum(messages)" if metrica == "messages" else "(sum(voice_seconds) / 60)"


@dataclass(frozen=True)
class ActivitySettings:
    ignored_channels: list[int] = field(default_factory=list)
    ignored_roles: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class ActivityRule:
    id: int
    guild_id: int
    role_id: int
    metric: str
    threshold: int
    period_days: int
    remove_when_below: bool


class ActivityStatsRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ scrittura
    async def flush(self, canali: dict, membri: dict, ore: dict) -> None:
        """Un lotto in una sola transazione: somma ai valori già presenti."""
        if not (canali or membri or ore):
            return
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for tabella, colonna, dati in (
                    ("activity_channel_daily", "channel_id", canali),
                    ("activity_member_daily", "user_id", membri),
                    ("activity_hour_daily", "hour", ore),
                ):
                    if not dati:
                        continue
                    await conn.executemany(
                        f"""
                        INSERT INTO {tabella} (guild_id, day, {colonna}, messages, voice_seconds)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (guild_id, day, {colonna}) DO UPDATE
                            SET messages = {tabella}.messages + EXCLUDED.messages,
                                voice_seconds = {tabella}.voice_seconds + EXCLUDED.voice_seconds
                        """,
                        [(g, d, k, v[0], v[1]) for (g, d, k), v in dati.items()],
                    )

    # -------------------------------------------------------------- lettura
    async def top_channels(self, guild_id: int, since: date, metrica: str, limite: int) -> list[tuple[int, int]]:
        righe = await self._pool.fetch(
            f"""
            SELECT channel_id, {_somma(metrica)}::bigint AS n FROM activity_channel_daily
            WHERE guild_id = $1 AND day >= $2 GROUP BY channel_id HAVING {_somma(metrica)} > 0
            ORDER BY n DESC, channel_id LIMIT $3
            """,
            guild_id, since, limite,
        )
        return [(r["channel_id"], r["n"]) for r in righe]

    async def top_members(
        self, guild_id: int, since: date, metrica: str, limite: int, solo_utenti: set[int] | None = None
    ) -> list[tuple[int, int]]:
        filtro = "AND user_id = ANY($4::bigint[])" if solo_utenti is not None else ""
        args = [guild_id, since, limite] + ([sorted(solo_utenti)] if solo_utenti is not None else [])
        righe = await self._pool.fetch(
            f"""
            SELECT user_id, {_somma(metrica)}::bigint AS n FROM activity_member_daily
            WHERE guild_id = $1 AND day >= $2 {filtro} GROUP BY user_id
            HAVING {_somma(metrica)} > 0 ORDER BY n DESC, user_id LIMIT $3
            """,
            *args,
        )
        return [(r["user_id"], r["n"]) for r in righe]

    async def member_total(self, guild_id: int, user_id: int, since: date, metrica: str) -> int:
        """Totale di un membro dal giorno `since` (anche per il requisito messaggi dei giveaway)."""
        return int(
            await self._pool.fetchval(
                f"SELECT COALESCE({_somma(metrica)}, 0) FROM activity_member_daily "
                "WHERE guild_id = $1 AND user_id = $2 AND day >= $3",
                guild_id, user_id, since,
            )
        )

    async def members_over(self, guild_id: int, since: date, metrica: str, soglia: int) -> set[int]:
        righe = await self._pool.fetch(
            f"""
            SELECT user_id FROM activity_member_daily WHERE guild_id = $1 AND day >= $2
            GROUP BY user_id HAVING {_somma(metrica)} >= $3
            """,
            guild_id, since, soglia,
        )
        return {r["user_id"] for r in righe}

    async def by_hour(self, guild_id: int, since: date, metrica: str = "messages") -> list[int]:
        righe = await self._pool.fetch(
            f"SELECT hour, {_somma(metrica)}::bigint AS n FROM activity_hour_daily "
            "WHERE guild_id = $1 AND day >= $2 GROUP BY hour",
            guild_id, since,
        )
        ore = [0] * 24
        for r in righe:
            ore[r["hour"]] = r["n"]
        return ore

    async def by_day(self, guild_id: int, since: date, metrica: str = "messages") -> dict[date, int]:
        righe = await self._pool.fetch(
            f"SELECT day, {_somma(metrica)}::bigint AS n FROM activity_hour_daily "
            "WHERE guild_id = $1 AND day >= $2 GROUP BY day",
            guild_id, since,
        )
        return {r["day"]: r["n"] for r in righe}

    async def last_activity(self, guild_id: int) -> tuple[date | None, int]:
        """(ultimo giorno con dati, messaggi contati oggi in totale degli ultimi 2 giorni)."""
        r = await self._pool.fetchrow(
            "SELECT max(day) AS ultimo, COALESCE(sum(messages) FILTER (WHERE day >= current_date - 1), 0) AS n "
            "FROM activity_hour_daily WHERE guild_id = $1",
            guild_id,
        )
        return r["ultimo"], int(r["n"])

    # ---------------------------------------------------------- impostazioni
    async def get_settings(self, guild_id: int) -> ActivitySettings:
        r = await self._pool.fetchrow(
            "SELECT ignored_channels, ignored_roles FROM activity_settings WHERE guild_id = $1", guild_id
        )
        return ActivitySettings(list(r["ignored_channels"]), list(r["ignored_roles"])) if r else ActivitySettings()

    async def _toggle(self, colonna: str, guild_id: int, valore: int) -> bool:
        """True se ora è ignorato, False se è stato rimesso. Un solo comando SQL (niente leggi-poi-scrivi)."""
        return bool(
            await self._pool.fetchval(
                f"""
                INSERT INTO activity_settings (guild_id, {colonna}) VALUES ($1, ARRAY[$2::bigint])
                ON CONFLICT (guild_id) DO UPDATE SET {colonna} = CASE
                    WHEN $2::bigint = ANY(activity_settings.{colonna})
                    THEN array_remove(activity_settings.{colonna}, $2::bigint)
                    ELSE array_append(activity_settings.{colonna}, $2::bigint) END
                RETURNING $2::bigint = ANY({colonna})
                """,
                guild_id, valore,
            )
        )

    async def toggle_ignored_channel(self, guild_id: int, channel_id: int) -> bool:
        return await self._toggle("ignored_channels", guild_id, channel_id)

    async def toggle_ignored_role(self, guild_id: int, role_id: int) -> bool:
        return await self._toggle("ignored_roles", guild_id, role_id)

    # ----------------------------------------------------------------- ruoli
    @staticmethod
    def _regola(r) -> ActivityRule:
        return ActivityRule(r["id"], r["guild_id"], r["role_id"], r["metric"], r["threshold"],
                            r["period_days"], r["remove_when_below"])

    async def add_rule(self, guild_id: int, role_id: int, metrica: str, soglia: int, giorni: int, rimuovi: bool) -> bool:
        """False se il server ha già il massimo di regole (lo stesso ruolo si aggiorna)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                esiste = await conn.fetchval(
                    "SELECT 1 FROM activity_roles WHERE guild_id = $1 AND role_id = $2", guild_id, role_id
                )
                if not esiste:
                    n = await conn.fetchval("SELECT count(*) FROM activity_roles WHERE guild_id = $1", guild_id)
                    if n >= MAX_REGOLE_PER_SERVER:
                        return False
                await conn.execute(
                    """
                    INSERT INTO activity_roles (guild_id, role_id, metric, threshold, period_days, remove_when_below)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (guild_id, role_id) DO UPDATE SET metric = EXCLUDED.metric,
                        threshold = EXCLUDED.threshold, period_days = EXCLUDED.period_days,
                        remove_when_below = EXCLUDED.remove_when_below
                    """,
                    guild_id, role_id, metrica, soglia, giorni, rimuovi,
                )
        return True

    async def delete_rule(self, guild_id: int, rule_id: int) -> bool:
        return (
            await self._pool.execute("DELETE FROM activity_roles WHERE guild_id = $1 AND id = $2", guild_id, rule_id)
        ) == "DELETE 1"

    async def list_rules(self, guild_id: int) -> list[ActivityRule]:
        righe = await self._pool.fetch("SELECT * FROM activity_roles WHERE guild_id = $1 ORDER BY id", guild_id)
        return [self._regola(r) for r in righe]

    async def guilds_with_rules(self) -> list[int]:
        return [r["guild_id"] for r in await self._pool.fetch("SELECT DISTINCT guild_id FROM activity_roles")]


def _get_pool():
    from core.database import db

    return db.pool


activity_stats_repo = ActivityStatsRepository(pool_provider=_get_pool)
