"""
core/repositories/voto_repo.py
==============================
Voti al bot, premio del server, riscatto e bonus XP. Un voto si scrive una volta (due richieste uguali del sito
pagano una volta sola: blocco per utente e sito, niente voto più vicino di 11 ore), si riscatta una volta sola in un
server (la riga si prende con FOR UPDATE SKIP LOCKED e si segna nella stessa transazione del premio). Monete e XP
passano da una sola scrittura; il premium a tempo si dà dopo, dal servizio dei codici.
Funzioni coperte: LIV-019, ECO-048, ECO-049, CFG-039
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import asyncpg

from core.leveling_logic import level_for_xp
from core.repositories.leveling_repo import add_coins_in
from core.voto_logic import GIORNI_PER_RISCATTARE, ORE_TRA_DUE_VOTI

CAMPI_IMPOSTAZIONI = frozenset({"attivo", "xp_bonus_pct", "xp_bonus_ore", "monete", "xp", "premium_giorni"})
SECONDI_CACHE_BONUS = 300


@dataclass(frozen=True)
class Premio:
    monete: int = 0
    xp: int = 0
    bonus_pct: int = 0
    bonus_ore: int = 0
    premium_giorni: int = 0


class VotoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache_bonus: dict[tuple[int, int], tuple[float, float]] = {}

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- impostazioni
    async def impostazioni(self, guild_id: int) -> asyncpg.Record:
        async with self._pool.acquire() as conn:
            await conn.execute("INSERT INTO voto_impostazioni (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
            return await conn.fetchrow("SELECT * FROM voto_impostazioni WHERE guild_id = $1", guild_id)

    async def imposta(self, guild_id: int, **campi) -> None:
        if not campi or not set(campi) <= CAMPI_IMPOSTAZIONI:
            raise ValueError("Campo non valido.")
        assegna = ", ".join(f"{n} = ${i + 2}" for i, n in enumerate(campi))  # nomi dalla lista bianca
        async with self._pool.acquire() as conn:
            await conn.execute("INSERT INTO voto_impostazioni (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
            await conn.execute(f"UPDATE voto_impostazioni SET {assegna} WHERE guild_id = $1", guild_id, *campi.values())

    # ---------------------------------------------------------------- voti
    async def registra(self, sito: str, user_id: int) -> int | None:
        """Scrive il voto. None se è lo stesso voto rinviato dal sito (meno di 11 ore dall'ultimo dello stesso sito)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"voto:{sito}:{user_id}")
                return await conn.fetchval(
                    "INSERT INTO voti (sito, user_id) SELECT $1, $2 WHERE NOT EXISTS "
                    "(SELECT 1 FROM voti WHERE sito = $1 AND user_id = $2 AND ricevuto_at > now() - make_interval(hours => $3)) RETURNING id",
                    sito, user_id, ORE_TRA_DUE_VOTI,
                )

    async def da_riscattare(self, user_id: int) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT count(*) FROM voti WHERE user_id = $1 AND riscattato_at IS NULL AND ricevuto_at > now() - make_interval(days => $2)",
                user_id, GIORNI_PER_RISCATTARE,
            )

    async def riscatta(self, guild_id: int, user_id: int, *, tetto_livello: int = 0, formula: str = "classica") -> Premio | None:
        """
        Un voto in attesa diventa il premio di questo server. None: nessun voto da riscattare o premio spento.
        Voto segnato e premio (monete, XP, bonus) stanno nella stessa transazione.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                i = await conn.fetchrow("SELECT * FROM voto_impostazioni WHERE guild_id = $1", guild_id)
                if i is None or not i["attivo"]:
                    return None
                voto = await conn.fetchval(
                    "SELECT id FROM voti WHERE user_id = $1 AND riscattato_at IS NULL AND ricevuto_at > now() - make_interval(days => $2) "
                    "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED", user_id, GIORNI_PER_RISCATTARE,
                )
                if voto is None:
                    return None
                await conn.execute("UPDATE voti SET riscattato_guild = $2, riscattato_at = now() WHERE id = $1", voto, guild_id)
                if i["monete"]:
                    await add_coins_in(conn, guild_id, user_id, i["monete"], classifica=False, motivo="voto")
                if i["xp"]:
                    xp = await conn.fetchval(
                        "INSERT INTO leveling_totals AS t (guild_id, user_id, xp_total) VALUES ($1, $2, $3) "
                        "ON CONFLICT (guild_id, user_id) DO UPDATE SET xp_total = t.xp_total + $3 RETURNING xp_total",
                        guild_id, user_id, i["xp"],
                    )
                    await conn.execute(
                        "UPDATE leveling_totals SET level = $3 WHERE guild_id = $1 AND user_id = $2", guild_id, user_id, level_for_xp(xp, tetto_livello, formula)
                    )
                if i["xp_bonus_pct"]:
                    await conn.execute(
                        "INSERT INTO voto_bonus (guild_id, user_id, fino_a, pct) VALUES ($1, $2, now() + make_interval(hours => $3), $4) "
                        "ON CONFLICT (guild_id, user_id) DO UPDATE SET fino_a = EXCLUDED.fino_a, pct = EXCLUDED.pct",
                        guild_id, user_id, i["xp_bonus_ore"], i["xp_bonus_pct"],
                    )
                    self._cache_bonus.pop((guild_id, user_id), None)
                return Premio(i["monete"], i["xp"], i["xp_bonus_pct"], i["xp_bonus_ore"], i["premium_giorni"])

    # ---------------------------------------------------------------- riscatto automatico (ECO-049)
    async def imposta_auto(self, user_id: int, guild_id: int | None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO voto_utenti (user_id, auto_guild) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET auto_guild = $2", user_id, guild_id
            )

    async def auto_di(self, user_id: int) -> int | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT auto_guild FROM voto_utenti WHERE user_id = $1", user_id)

    # ---------------------------------------------------------------- bonus XP (LIV-019)
    async def fattore_xp(self, guild_id: int, user_id: int) -> float:
        """1.0 senza bonus; 1.10 con +10%. Letto al massimo ogni 5 minuti per persona e server."""
        chiave = (guild_id, user_id)
        adesso = time.monotonic()
        visto = self._cache_bonus.get(chiave)
        if visto is not None and adesso - visto[0] < SECONDI_CACHE_BONUS:
            return visto[1]
        async with self._pool.acquire() as conn:
            pct = await conn.fetchval("SELECT pct FROM voto_bonus WHERE guild_id = $1 AND user_id = $2 AND fino_a > now()", guild_id, user_id)
        fattore = 1.0 + (pct or 0) / 100
        if len(self._cache_bonus) > 20_000:
            self._cache_bonus.clear()
        self._cache_bonus[chiave] = (adesso, fattore)
        return fattore


def _get_pool():
    from core.database import db

    return db.pool


voto_repo = VotoRepository(pool_provider=_get_pool)
