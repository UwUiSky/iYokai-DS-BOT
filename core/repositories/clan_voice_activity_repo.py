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
Le scritture del worker sono raggruppate per server (M 9.18, PERF-4).
Funzioni coperte: SPEC §15.14
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

    async def apply_ticks(
        self, voci: list[tuple[int, int, int]], today: date
    ) -> list[tuple[int, int]]:
        """
        Un tick per ogni (clan_id, user_id, channel_id) di `voci`, in QUESTO
        giorno, tutti in una transazione (M 9.18, PERF-4: una lettura e una
        scrittura per server invece di una transazione per membro).
        Per ogni voce: stato precedente letto sotto blocco; i contatori si
        azzerano se cambia il canale (decadimento) o il giorno (tetto
        giornaliero); la ricompensa (core.guild_clan_logic.compute_tick_reward)
        usa i contatori PRIMA del tick; poi i contatori salgono di uno.

        Restituisce (xp, coin) di ogni voce, nello stesso ordine. La
        tesoreria la accredita il chiamante (GuildClanRepository).
        """
        if not voci:
            return []
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    """
                    SELECT * FROM clan_voice_activity
                    WHERE (clan_id, user_id) IN (
                        SELECT * FROM unnest($1::bigint[], $2::bigint[])
                    )
                    ORDER BY clan_id, user_id
                    FOR UPDATE
                    """,
                    [v[0] for v in voci],
                    [v[1] for v in voci],
                )
                prima = {(r["clan_id"], r["user_id"]): r for r in righe}
                risultati: list[tuple[int, int]] = []
                nuove = []
                for clan_id, user_id, channel_id in voci:
                    row = prima.get((clan_id, user_id))
                    if row is None:
                        ticks_in_channel_prima = ticks_oggi_prima = 0
                    else:
                        stesso_canale = row["current_channel_id"] == channel_id
                        stesso_giorno = row["activity_date"] == today
                        ticks_in_channel_prima = row["ticks_in_current_channel"] if stesso_canale else 0
                        ticks_oggi_prima = row["ticks_today"] if stesso_giorno else 0
                    risultati.append(
                        compute_tick_reward(
                            ticks_in_same_channel=ticks_in_channel_prima,
                            ticks_today=ticks_oggi_prima,
                        )
                    )
                    nuove.append(
                        (clan_id, user_id, channel_id, ticks_in_channel_prima + 1, ticks_oggi_prima + 1, today)
                    )
                await conn.executemany(
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
                    nuove,
                )
        return risultati

    async def clear_activities(self, coppie: list[tuple[int, int]]) -> None:
        """
        Chi è uscito dal vocale (non idoneo finché non rientra): canale a
        NULL, senza toccare ticks_today (il tetto giornaliero resta fino a
        mezzanotte). Una sola istruzione per tutte le coppie (clan, utente).
        """
        if not coppie:
            return
        await self._pool.execute(
            """
            UPDATE clan_voice_activity
            SET current_channel_id = NULL, ticks_in_current_channel = 0
            WHERE (clan_id, user_id) IN (SELECT * FROM unnest($1::bigint[], $2::bigint[]))
            """,
            [c for c, _ in coppie],
            [u for _, u in coppie],
        )

    async def get_tracked_as_in_voice(self) -> list[tuple[int, int]]:
        """(clan_id, user_id) di OGNI riga che risulta ancora "in
        vocale" (current_channel_id non nullo) secondo l'ultimo tick
        registrato — usata dal worker per capire chi è uscito dal
        vocale dall'ultimo giro (non più tra i membri live trovati
        in nessun canale) e va quindi ripulito con clear_activities()."""
        rows = await self._pool.fetch(
            "SELECT clan_id, user_id FROM clan_voice_activity WHERE current_channel_id IS NOT NULL"
        )
        return [(r["clan_id"], r["user_id"]) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


clan_voice_activity_repo = ClanVoiceActivityRepository(pool_provider=_get_pool)
