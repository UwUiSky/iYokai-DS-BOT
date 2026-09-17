"""
core/repositories/leveling_repo.py
=====================================
Persistenza di XP, livelli, economia e classifiche.

Due tabelle, con scopi distinti:
- leveling_totals: lo stato "vivo" per utente — XP e coin
  CUMULATIVI di sempre (per la classifica all-time e per calcolare
  il livello attuale), più lo stato tecnico per il cooldown testuale
  e per il conteggio vocale (canale corrente, minuti consecutivi,
  minuti di oggi, cooldown daily/work)
- leveling_activity: righe PER PERIODO (period_key, vedi
  core/leveling_logic.py) con quanto guadagnato IN QUEL MESE — è la
  tabella su cui si basa la classifica mensile, e non richiede mai
  un reset: un nuovo mese è semplicemente un nuovo period_key senza
  righe ancora scritte
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import asyncpg

from core.leveling_logic import (
    can_earn_text_xp,
    compute_voice_minute,
    did_level_up,
    level_for_xp,
    period_key,
    TEXT_XP_AMOUNT,
)


@dataclass(frozen=True)
class TextXpResult:
    granted: bool
    new_xp_total: int
    leveled_up: bool
    new_level: int


@dataclass(frozen=True)
class VoiceMinuteGrant:
    xp_granted: int
    coins_granted: int
    leveled_up: bool
    new_level: int


@dataclass(frozen=True)
class UserTotals:
    guild_id: int
    user_id: int
    xp_total: int
    level: int
    coins_total: int
    last_daily_at: datetime | None
    last_work_at: datetime | None


@dataclass(frozen=True)
class LeaderboardEntry:
    user_id: int
    amount: int


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS leveling_totals (
            guild_id                  BIGINT NOT NULL,
            user_id                   BIGINT NOT NULL,
            xp_total                  BIGINT NOT NULL DEFAULT 0,
            level                     INTEGER NOT NULL DEFAULT 0,
            coins_total                BIGINT NOT NULL DEFAULT 0,
            last_text_xp_at           TIMESTAMPTZ,
            last_daily_at             TIMESTAMPTZ,
            last_work_at              TIMESTAMPTZ,
            voice_channel_id          BIGINT,
            voice_consecutive_minutes INTEGER NOT NULL DEFAULT 0,
            voice_minutes_today       INTEGER NOT NULL DEFAULT 0,
            voice_activity_date       DATE,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS leveling_activity (
            guild_id   BIGINT NOT NULL,
            user_id    BIGINT NOT NULL,
            period_key TEXT NOT NULL,
            xp         BIGINT NOT NULL DEFAULT 0,
            coins      BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, period_key)
        );

        -- Le classifiche ordinano per xp/coins DESC filtrando su
        -- guild_id (e, per quella mensile, anche su period_key):
        -- questi indici servono esattamente quella query.
        CREATE INDEX IF NOT EXISTS idx_leveling_totals_guild_xp
            ON leveling_totals (guild_id, xp_total DESC);
        CREATE INDEX IF NOT EXISTS idx_leveling_totals_guild_coins
            ON leveling_totals (guild_id, coins_total DESC);
        CREATE INDEX IF NOT EXISTS idx_leveling_activity_guild_period_xp
            ON leveling_activity (guild_id, period_key, xp DESC);
        CREATE INDEX IF NOT EXISTS idx_leveling_activity_guild_period_coins
            ON leveling_activity (guild_id, period_key, coins DESC);
        """
    )


class LevelingRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_totals(self, guild_id: int, user_id: int) -> UserTotals:
        row = await self._pool.fetchrow(
            """
            SELECT xp_total, level, coins_total, last_daily_at, last_work_at
            FROM leveling_totals WHERE guild_id = $1 AND user_id = $2
            """,
            guild_id,
            user_id,
        )
        if row is None:
            return UserTotals(guild_id, user_id, 0, 0, 0, None, None)
        return UserTotals(
            guild_id=guild_id,
            user_id=user_id,
            xp_total=row["xp_total"],
            level=row["level"],
            coins_total=row["coins_total"],
            last_daily_at=row["last_daily_at"],
            last_work_at=row["last_work_at"],
        )

    async def _add_period_activity(
        self, conn: asyncpg.Connection, guild_id: int, user_id: int, xp: int, coins: int
    ) -> None:
        if xp == 0 and coins == 0:
            return
        await conn.execute(
            """
            INSERT INTO leveling_activity (guild_id, user_id, period_key, xp, coins)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id, user_id, period_key) DO UPDATE
                SET xp = leveling_activity.xp + EXCLUDED.xp,
                    coins = leveling_activity.coins + EXCLUDED.coins
            """,
            guild_id,
            user_id,
            period_key(),
            xp,
            coins,
        )

    async def add_text_xp(self, guild_id: int, user_id: int) -> TextXpResult:
        """
        Assegna XP testuale se il cooldown lo consente. Tutto dentro
        una transazione per evitare che due messaggi arrivati quasi
        insieme (stesso utente, connessioni diverse del bot in un
        futuro multi-processo) leggano lo stesso "last_text_xp_at"
        prima che l'uno o l'altro lo aggiorni.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT xp_total, last_text_xp_at FROM leveling_totals
                    WHERE guild_id = $1 AND user_id = $2 FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                )
                xp_before = row["xp_total"] if row else 0
                last_xp_at = row["last_text_xp_at"] if row else None

                now = datetime.now(timezone.utc)
                if not can_earn_text_xp(last_xp_at, now):
                    return TextXpResult(
                        granted=False, new_xp_total=xp_before, leveled_up=False,
                        new_level=level_for_xp(xp_before),
                    )

                xp_after = xp_before + TEXT_XP_AMOUNT
                leveled_up, new_level = did_level_up(xp_before, xp_after)

                await conn.execute(
                    """
                    INSERT INTO leveling_totals (guild_id, user_id, xp_total, level, last_text_xp_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET xp_total = $3, level = $4, last_text_xp_at = $5
                    """,
                    guild_id,
                    user_id,
                    xp_after,
                    new_level,
                    now,
                )
                await self._add_period_activity(conn, guild_id, user_id, TEXT_XP_AMOUNT, 0)

                return TextXpResult(
                    granted=True, new_xp_total=xp_after, leveled_up=leveled_up, new_level=new_level
                )

    async def add_voice_minute(
        self, guild_id: int, user_id: int, current_channel_id: int, is_eligible: bool
    ) -> VoiceMinuteGrant | None:
        """
        Registra un minuto di presenza vocale. Se `is_eligible` è
        False (una delle regole anti-farm non è soddisfatta), il
        canale corrente viene comunque tracciato — serve per sapere
        se il PROSSIMO minuto idoneo rappresenta un cambio di canale
        — ma non viene assegnato nulla e la funzione restituisce
        None. Il rollover del contatore giornaliero (mezzanotte UTC)
        viene gestito qui, indipendentemente dall'idoneità.
        """
        today = date.today()
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT xp_total, voice_channel_id, voice_consecutive_minutes,
                           voice_minutes_today, voice_activity_date
                    FROM leveling_totals WHERE guild_id = $1 AND user_id = $2 FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                )
                xp_before = row["xp_total"] if row else 0
                stored_channel_id = row["voice_channel_id"] if row else None
                stored_consecutive = row["voice_consecutive_minutes"] if row else 0
                stored_date = row["voice_activity_date"] if row else None

                # Rollover giornaliero: un nuovo giorno azzera i
                # minuti di oggi, a prescindere dall'idoneità di
                # questo specifico minuto.
                minutes_today = row["voice_minutes_today"] if row and stored_date == today else 0

                changed_channel = stored_channel_id != current_channel_id

                if not is_eligible:
                    await conn.execute(
                        """
                        INSERT INTO leveling_totals
                            (guild_id, user_id, voice_channel_id, voice_minutes_today, voice_activity_date)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (guild_id, user_id) DO UPDATE
                            SET voice_channel_id = $3,
                                voice_minutes_today = $4,
                                voice_activity_date = $5
                        """,
                        guild_id,
                        user_id,
                        current_channel_id,
                        minutes_today,
                        today,
                    )
                    return None

                result = compute_voice_minute(stored_consecutive, minutes_today, changed_channel)
                xp_after = xp_before + result.xp_granted
                leveled_up, new_level = did_level_up(xp_before, xp_after)

                await conn.execute(
                    """
                    INSERT INTO leveling_totals
                        (guild_id, user_id, xp_total, level, coins_total,
                         voice_channel_id, voice_consecutive_minutes,
                         voice_minutes_today, voice_activity_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET xp_total = $3, level = $4,
                            coins_total = leveling_totals.coins_total + $5,
                            voice_channel_id = $6,
                            voice_consecutive_minutes = $7,
                            voice_minutes_today = $8,
                            voice_activity_date = $9
                    """,
                    guild_id,
                    user_id,
                    xp_after,
                    new_level,
                    result.coins_granted,
                    current_channel_id,
                    result.new_consecutive_minutes,
                    result.new_minutes_today,
                    today,
                )
                await self._add_period_activity(
                    conn, guild_id, user_id, result.xp_granted, result.coins_granted
                )

                return VoiceMinuteGrant(
                    xp_granted=result.xp_granted,
                    coins_granted=result.coins_granted,
                    leveled_up=leveled_up,
                    new_level=new_level,
                )

    async def add_coins(self, guild_id: int, user_id: int, amount: int) -> int:
        """Aggiunge (o sottrae, con amount negativo) coin. Restituisce il nuovo saldo."""
        row = await self._pool.fetchrow(
            """
            INSERT INTO leveling_totals (guild_id, user_id, coins_total)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET coins_total = leveling_totals.coins_total + $3
            RETURNING coins_total
            """,
            guild_id,
            user_id,
            amount,
        )
        await self._pool.execute(
            """
            INSERT INTO leveling_activity (guild_id, user_id, period_key, coins)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id, period_key) DO UPDATE
                SET coins = leveling_activity.coins + $4
            """,
            guild_id,
            user_id,
            period_key(),
            amount,
        )
        return row["coins_total"]

    async def transfer_coins(
        self, guild_id: int, from_user_id: int, to_user_id: int, amount: int
    ) -> bool:
        """
        Trasferisce coin da un utente all'altro, atomicamente e solo
        se il mittente ha saldo sufficiente. Restituisce False (senza
        scrivere nulla) se il saldo non basta — mai un saldo negativo.
        """
        if amount <= 0:
            raise ValueError("L'importo da trasferire deve essere positivo.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                saldo = await conn.fetchval(
                    """
                    SELECT coins_total FROM leveling_totals
                    WHERE guild_id = $1 AND user_id = $2 FOR UPDATE
                    """,
                    guild_id,
                    from_user_id,
                ) or 0

                if saldo < amount:
                    return False

                await conn.execute(
                    """
                    INSERT INTO leveling_totals (guild_id, user_id, coins_total)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET coins_total = leveling_totals.coins_total + $3
                    """,
                    guild_id,
                    from_user_id,
                    -amount,
                )
                await conn.execute(
                    """
                    INSERT INTO leveling_totals (guild_id, user_id, coins_total)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET coins_total = leveling_totals.coins_total + $3
                    """,
                    guild_id,
                    to_user_id,
                    amount,
                )
                return True

    async def set_last_daily(self, guild_id: int, user_id: int, when: datetime) -> None:
        await self._pool.execute(
            """
            INSERT INTO leveling_totals (guild_id, user_id, last_daily_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET last_daily_at = $3
            """,
            guild_id,
            user_id,
            when,
        )

    async def set_last_work(self, guild_id: int, user_id: int, when: datetime) -> None:
        await self._pool.execute(
            """
            INSERT INTO leveling_totals (guild_id, user_id, last_work_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET last_work_at = $3
            """,
            guild_id,
            user_id,
            when,
        )

    async def top_xp_alltime(self, guild_id: int, limit: int = 10) -> list[LeaderboardEntry]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, xp_total AS amount FROM leveling_totals
            WHERE guild_id = $1 AND xp_total > 0
            ORDER BY xp_total DESC LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [LeaderboardEntry(r["user_id"], r["amount"]) for r in rows]

    async def top_coins_alltime(self, guild_id: int, limit: int = 10) -> list[LeaderboardEntry]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, coins_total AS amount FROM leveling_totals
            WHERE guild_id = $1 AND coins_total > 0
            ORDER BY coins_total DESC LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [LeaderboardEntry(r["user_id"], r["amount"]) for r in rows]

    async def top_xp_period(
        self, guild_id: int, limit: int = 10, period: str | None = None
    ) -> list[LeaderboardEntry]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, xp AS amount FROM leveling_activity
            WHERE guild_id = $1 AND period_key = $2 AND xp > 0
            ORDER BY xp DESC LIMIT $3
            """,
            guild_id,
            period or period_key(),
            limit,
        )
        return [LeaderboardEntry(r["user_id"], r["amount"]) for r in rows]

    async def top_coins_period(
        self, guild_id: int, limit: int = 10, period: str | None = None
    ) -> list[LeaderboardEntry]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, coins AS amount FROM leveling_activity
            WHERE guild_id = $1 AND period_key = $2 AND coins > 0
            ORDER BY coins DESC LIMIT $3
            """,
            guild_id,
            period or period_key(),
            limit,
        )
        return [LeaderboardEntry(r["user_id"], r["amount"]) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


leveling_repo = LevelingRepository(pool_provider=_get_pool)
