"""
core/repositories/clan_voice_activity_repo.py
==================================================
Stato per-membro-per-clan del tick vocale (SPEC.md §15.14) — quale
canale, da quanti tick consecutivi (per il decadimento), quanti tick
oggi (per il tetto giornaliero). Giorno in UTC, coerente con
core.leveling_logic.period_key() che usa la stessa convenzione nel
resto del progetto.

Una riga per (clan_id, user_id): un utente può maturare tick per un
SOLO clan alla volta (coerente con "un utente sta in un solo clan
per server", get_member_clan_in_guild in guild_clan_repo.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import asyncpg

from core.guild_clan_logic import compute_tick_reward


@dataclass(frozen=True)
class ClanVoiceActivity:
    clan_id: int
    user_id: int
    current_channel_id: int | None
    ticks_in_current_channel: int
    ticks_today: int
    activity_date: date


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS clan_voice_activity (
            clan_id                    INTEGER NOT NULL,
            user_id                    BIGINT NOT NULL,
            current_channel_id         BIGINT,
            ticks_in_current_channel   INTEGER NOT NULL DEFAULT 0,
            ticks_today                INTEGER NOT NULL DEFAULT 0,
            activity_date               DATE NOT NULL DEFAULT CURRENT_DATE,
            PRIMARY KEY (clan_id, user_id)
        );
        """
    )


class ClanVoiceActivityRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_activity(self, row) -> ClanVoiceActivity:
        return ClanVoiceActivity(
            clan_id=row["clan_id"],
            user_id=row["user_id"],
            current_channel_id=row["current_channel_id"],
            ticks_in_current_channel=row["ticks_in_current_channel"],
            ticks_today=row["ticks_today"],
            activity_date=row["activity_date"],
        )

    async def get_activity(self, clan_id: int, user_id: int) -> ClanVoiceActivity | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM clan_voice_activity WHERE clan_id = $1 AND user_id = $2",
            clan_id, user_id,
        )
        return self._row_to_activity(row) if row is not None else None

    async def apply_tick(
        self, clan_id: int, user_id: int, channel_id: int, today: date
    ) -> tuple[int, int]:
        """
        UN tick per questo membro, in QUESTO canale, in QUESTO
        giorno. Legge lo stato precedente, decide se azzerare i
        contatori (cambio canale rispetto all'ultimo tick noto,
        oppure giorno diverso — il tetto giornaliero riparte da
        zero), calcola la ricompensa con la logica pura già
        committata (core/guild_clan_logic.compute_tick_reward,
        basata sui contatori PRIMA di questo tick), poi scrive il
        nuovo stato con i contatori incrementati di uno. Tutto in
        una transazione, per non lasciare mai lo stato a metà tra
        una lettura e la scrittura successiva.

        Restituisce (xp, coin) guadagnati in QUESTO tick — il
        chiamante li accredita alla tesoreria del clan separatamente
        (questo repository non tocca la tesoreria, resta la
        responsabilità di GuildClanRepository).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT * FROM clan_voice_activity
                    WHERE clan_id = $1 AND user_id = $2 FOR UPDATE
                    """,
                    clan_id, user_id,
                )

                if row is None:
                    ticks_in_channel_prima = 0
                    ticks_oggi_prima = 0
                else:
                    stesso_canale = row["current_channel_id"] == channel_id
                    stesso_giorno = row["activity_date"] == today
                    ticks_in_channel_prima = (
                        row["ticks_in_current_channel"] if stesso_canale else 0
                    )
                    ticks_oggi_prima = row["ticks_today"] if stesso_giorno else 0

                xp, coin = compute_tick_reward(
                    ticks_in_same_channel=ticks_in_channel_prima, ticks_today=ticks_oggi_prima
                )

                await conn.execute(
                    """
                    INSERT INTO clan_voice_activity
                        (clan_id, user_id, current_channel_id,
                         ticks_in_current_channel, ticks_today, activity_date)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (clan_id, user_id) DO UPDATE
                        SET current_channel_id = EXCLUDED.current_channel_id,
                            ticks_in_current_channel = EXCLUDED.ticks_in_current_channel,
                            ticks_today = EXCLUDED.ticks_today,
                            activity_date = EXCLUDED.activity_date
                    """,
                    clan_id, user_id, channel_id,
                    ticks_in_channel_prima + 1, ticks_oggi_prima + 1, today,
                )

        return xp, coin

    async def clear_activity(self, clan_id: int, user_id: int) -> None:
        """Usata quando un membro esce dal vocale (non idoneo per
        nessun tick finché non rientra) — resetta il canale a NULL
        senza toccare ticks_today (il tetto giornaliero resta valido
        fino a mezzanotte, non si azzera uscendo dal vocale)."""
        await self._pool.execute(
            """
            UPDATE clan_voice_activity
            SET current_channel_id = NULL, ticks_in_current_channel = 0
            WHERE clan_id = $1 AND user_id = $2
            """,
            clan_id, user_id,
        )


def _get_pool():
    from core.database import db
    return db.pool


clan_voice_activity_repo = ClanVoiceActivityRepository(pool_provider=_get_pool)
