"""
core/repositories/birthday_repo.py
==================================
Compleanni (solo giorno e mese) e impostazioni degli auguri (NF-26).
Tabelle: core/migrations/0088_birthdays.sql.
Funzioni coperte: SPEC §23 (NF-26)
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import asyncpg

from core.birthday_logic import MESSAGGIO_DI_BASE


@dataclass(frozen=True)
class BirthdayConfig:
    guild_id: int
    channel_id: int | None
    role_id: int | None
    message: str
    ping_ruoli: bool


class BirthdayRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def set_birthday(self, guild_id: int, user_id: int, day: int, month: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO birthdays (guild_id, user_id, day, month) VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET day = EXCLUDED.day, month = EXCLUDED.month,
                    last_announced_year = CASE WHEN birthdays.day = EXCLUDED.day AND birthdays.month = EXCLUDED.month
                                               THEN birthdays.last_announced_year END
            """,
            guild_id, user_id, day, month,
        )

    async def get_birthday(self, guild_id: int, user_id: int) -> tuple[int, int] | None:
        r = await self._pool.fetchrow(
            "SELECT day, month FROM birthdays WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return None if r is None else (r["day"], r["month"])

    async def remove_birthday(self, guild_id: int, user_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM birthdays WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return esito.endswith(" 1")

    async def claim_due(self, guild_id: int, oggi: date) -> list[int]:
        """
        Gli utenti che festeggiano oggi e non hanno ancora ricevuto gli auguri quest'anno,
        segnati come serviti nella stessa query (due giri insieme non li servono due volte).
        """
        giorno_29 = oggi.month == 2 and oggi.day == 28 and not calendar.isleap(oggi.year)
        righe = await self._pool.fetch(
            """
            UPDATE birthdays SET last_announced_year = $2
            WHERE guild_id = $1
              AND ((month = $4 AND day = $3) OR ($5 AND month = 2 AND day = 29))
              AND last_announced_year IS DISTINCT FROM $2
            RETURNING user_id
            """,
            guild_id, oggi.year, oggi.day, oggi.month, giorno_29,
        )
        return [r["user_id"] for r in righe]

    async def release_claim(self, guild_id: int, user_ids: list[int], year: int) -> None:
        """Gli auguri non sono partiti: si potrà riprovare."""
        await self._pool.execute(
            "UPDATE birthdays SET last_announced_year = NULL "
            "WHERE guild_id = $1 AND user_id = ANY($2::bigint[]) AND last_announced_year = $3",
            guild_id, user_ids, year,
        )

    async def get_config(self, guild_id: int) -> BirthdayConfig:
        r = await self._pool.fetchrow(
            "SELECT guild_id, channel_id, role_id, message, ping_ruoli FROM birthday_config WHERE guild_id = $1",
            guild_id,
        )
        if r is None:
            return BirthdayConfig(guild_id, None, None, MESSAGGIO_DI_BASE, False)
        return BirthdayConfig(**dict(r))

    async def set_channel(self, guild_id: int, channel_id: int | None, message: str | None, ping_ruoli: bool) -> None:
        await self._pool.execute(
            """
            INSERT INTO birthday_config (guild_id, channel_id, message, ping_ruoli)
            VALUES ($1, $2, COALESCE($3, $5), $4)
            ON CONFLICT (guild_id) DO UPDATE
                SET channel_id = EXCLUDED.channel_id,
                    message = COALESCE($3, birthday_config.message),
                    ping_ruoli = CASE WHEN $3 IS NULL THEN birthday_config.ping_ruoli ELSE EXCLUDED.ping_ruoli END
            """,
            guild_id, channel_id, message, ping_ruoli, MESSAGGIO_DI_BASE,
        )

    async def set_role(self, guild_id: int, role_id: int | None) -> None:
        await self._pool.execute(
            """
            INSERT INTO birthday_config (guild_id, role_id) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET role_id = EXCLUDED.role_id
            """,
            guild_id, role_id,
        )

    async def list_active_configs(self) -> list[BirthdayConfig]:
        righe = await self._pool.fetch(
            "SELECT guild_id, channel_id, role_id, message, ping_ruoli FROM birthday_config "
            "WHERE channel_id IS NOT NULL ORDER BY guild_id"
        )
        return [BirthdayConfig(**dict(r)) for r in righe]


def _get_pool():
    from core.database import db
    return db.pool


birthday_repo = BirthdayRepository(pool_provider=_get_pool)
