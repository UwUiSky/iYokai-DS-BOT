"""
core/repositories/contenuti_repo.py
===================================
Premi di quiz e impiccato con tetto giornaliero (ECO-113, ECO-114), righe del profilo (ECO-152) e comandi di
guadagno creati dal server (ECO-039). Il tetto sta dentro la transazione: la riga del giorno si blocca prima di
leggere quanto è già stato dato, quindi due premi insieme non superano il tetto.
Funzioni coperte: ECO-039, ECO-113, ECO-114, ECO-152
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import asyncpg

from core.repositories.leveling_repo import add_coins_in

MAX_COMANDI_GUADAGNO = 10
RIGHE_PROFILO = ("monete", "banca", "animali", "partner", "prestigio", "amici")
MAX_RIGHE_PROFILO = len(RIGHE_PROFILO)


@dataclass(frozen=True)
class ComandoGuadagno:
    nome: str
    minimo: int
    massimo: int
    pausa_s: int
    testo: str


class ContenutiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- premi con tetto (ECO-113, 114)
    async def premia(self, guild_id: int, user_id: int, tipo: str, importo: int, tetto: int, giorno: date | None = None) -> int:
        """Dà fino a `importo` monete restando dentro `tetto` per il giorno (UTC). Restituisce quante ne ha date (anche 0)."""
        if importo <= 0 or tetto <= 0:
            raise ValueError("Importo o tetto non validi.")
        giorno = giorno or datetime.now(timezone.utc).date()
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                prima = await conn.fetchval(
                    "INSERT INTO economia_premi_giorno (guild_id, user_id, giorno, tipo, totale) VALUES ($1, $2, $3, $4, 0) "
                    "ON CONFLICT (guild_id, user_id, giorno, tipo) DO UPDATE SET totale = economia_premi_giorno.totale RETURNING totale",
                    guild_id, user_id, giorno, tipo,
                )
                da_dare = min(importo, tetto - prima)
                if da_dare <= 0:
                    return 0
                await conn.execute(
                    "UPDATE economia_premi_giorno SET totale = totale + $5 WHERE guild_id = $1 AND user_id = $2 AND giorno = $3 AND tipo = $4",
                    guild_id, user_id, giorno, tipo, da_dare,
                )
                await add_coins_in(conn, guild_id, user_id, da_dare, classifica=False, motivo=tipo)
                return da_dare

    # ---------------------------------------------------------------- righe del profilo (ECO-152)
    async def imposta_righe(self, guild_id: int, user_id: int, righe: list[str]) -> None:
        await self._pool.execute(
            "INSERT INTO economia_profilo_righe (guild_id, user_id, righe) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET righe = EXCLUDED.righe", guild_id, user_id, ",".join(righe),
        )

    async def righe(self, guild_id: int, user_id: int) -> list[str]:
        """Le righe scelte, nell'ordine scelto; se non ha scelto niente, tutte."""
        t = await self._pool.fetchval("SELECT righe FROM economia_profilo_righe WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
        if t is None:
            return list(RIGHE_PROFILO)
        return [r for r in t.split(",") if r in RIGHE_PROFILO]

    # ---------------------------------------------------------------- comandi di guadagno (ECO-039)
    async def crea_comando(self, guild_id: int, nome: str, minimo: int, massimo: int, pausa_s: int, testo: str, autore: int) -> str:
        """'ok' | 'troppi' | 'esiste'."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                if await conn.fetchval("SELECT count(*) FROM economia_comandi_guadagno WHERE guild_id = $1", guild_id) >= MAX_COMANDI_GUADAGNO:
                    return "troppi"
                r = await conn.fetchval(
                    "INSERT INTO economia_comandi_guadagno (guild_id, nome, minimo, massimo, pausa_s, testo, creato_da) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT DO NOTHING RETURNING 1",
                    guild_id, nome, minimo, massimo, pausa_s, testo, autore,
                )
                return "ok" if r else "esiste"

    async def togli_comando(self, guild_id: int, nome: str) -> bool:
        r = await self._pool.execute("DELETE FROM economia_comandi_guadagno WHERE guild_id = $1 AND nome = $2", guild_id, nome)
        return r.endswith(" 1")

    async def comandi(self, guild_id: int) -> list[ComandoGuadagno]:
        righe = await self._pool.fetch(
            "SELECT nome, minimo, massimo, pausa_s, testo FROM economia_comandi_guadagno WHERE guild_id = $1 ORDER BY nome LIMIT 25", guild_id
        )
        return [ComandoGuadagno(**dict(r)) for r in righe]

    async def comando(self, guild_id: int, nome: str) -> ComandoGuadagno | None:
        r = await self._pool.fetchrow(
            "SELECT nome, minimo, massimo, pausa_s, testo FROM economia_comandi_guadagno WHERE guild_id = $1 AND nome = $2", guild_id, nome
        )
        return ComandoGuadagno(**dict(r)) if r else None


def _get_pool():
    from core.database import db

    return db.pool


contenuti_repo = ContenutiRepository(pool_provider=_get_pool)
