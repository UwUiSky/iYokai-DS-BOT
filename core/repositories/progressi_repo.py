"""
core/repositories/progressi_repo.py
===================================
Tabelle progress_missioni, progress_serie, progress_traguardi, progress_stagione.
Le ricompense in monete le accredita il servizio (core/progressi_service.py).
Funzioni coperte: SPEC §23.17 (D49)
"""

from __future__ import annotations

from datetime import date

import asyncpg

from core.progressi_logic import STAGIONE_GRADINI, aggiorna_serie
from core.repositories.leveling_repo import add_coins_in


class ProgressiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---- missioni ----
    async def aggiungi_progressi(self, righe: list[tuple[int, int, date, str, int, int]]) -> None:
        """(server, utente, giorno, chiave, quantità, obiettivo): il progresso si ferma all'obiettivo."""
        if not righe:
            return
        await self._pool.executemany(
            """
            INSERT INTO progress_missioni (guild_id, user_id, giorno, chiave, progresso)
            VALUES ($1, $2, $3, $4, LEAST($5::int, $6::int))
            ON CONFLICT (guild_id, user_id, giorno, chiave) DO UPDATE
                SET progresso = LEAST(progress_missioni.progresso + $5::int, $6::int)
            """,
            righe,
        )

    async def missioni_di(self, guild_id: int, user_id: int, giorno: date) -> dict[str, tuple[int, bool]]:
        righe = await self._pool.fetch(
            "SELECT chiave, progresso, riscattata FROM progress_missioni "
            "WHERE guild_id = $1 AND user_id = $2 AND giorno = $3",
            guild_id, user_id, giorno,
        )
        return {r["chiave"]: (r["progresso"], r["riscattata"]) for r in righe}

    async def riscatta_missioni(
        self, guild_id: int, user_id: int, giorno: date, missioni: list[tuple[str, int, int]]
    ) -> tuple[int, int]:
        """
        `missioni` = (chiave, obiettivo, premio). Segna come riscosse quelle finite e le paga, nella
        stessa transazione: un premio esce una sola volta. Restituisce (monete, quante).
        """
        monete = quanti = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for chiave, obiettivo, premio in missioni:
                    riga = await conn.fetchrow(
                        """
                        UPDATE progress_missioni SET riscattata = TRUE
                        WHERE guild_id = $1 AND user_id = $2 AND giorno = $3 AND chiave = $4
                          AND NOT riscattata AND progresso >= $5
                        RETURNING 1
                        """,
                        guild_id, user_id, giorno, chiave, obiettivo,
                    )
                    if riga is not None:
                        monete += premio
                        quanti += 1
                if monete:
                    await add_coins_in(conn, guild_id, user_id, monete)
        return monete, quanti

    async def missioni_completate(self, guild_id: int, user_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM progress_missioni WHERE guild_id = $1 AND user_id = $2 AND riscattata",
            guild_id, user_id,
        )

    # ---- serie ----
    async def registra_riscossione(self, guild_id: int, user_id: int, oggi: date) -> tuple[int, int, bool]:
        """Una riscossione giornaliera. Restituisce (serie, record, True se è un giorno nuovo)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO progress_serie (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    guild_id, user_id,
                )
                riga = await conn.fetchrow(
                    "SELECT serie, record, ultimo_giorno FROM progress_serie "
                    "WHERE guild_id = $1 AND user_id = $2 FOR UPDATE",
                    guild_id, user_id,
                )
                serie, record, ultimo = aggiorna_serie(riga["serie"], riga["record"], riga["ultimo_giorno"], oggi)
                nuovo_giorno = riga["ultimo_giorno"] != oggi
                await conn.execute(
                    "UPDATE progress_serie SET serie = $3, record = $4, ultimo_giorno = $5 "
                    "WHERE guild_id = $1 AND user_id = $2",
                    guild_id, user_id, serie, record, ultimo,
                )
        return serie, record, nuovo_giorno

    async def serie_di(self, guild_id: int, user_id: int) -> tuple[int, int, date | None]:
        riga = await self._pool.fetchrow(
            "SELECT serie, record, ultimo_giorno FROM progress_serie WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        return (riga["serie"], riga["record"], riga["ultimo_giorno"]) if riga else (0, 0, None)

    # ---- traguardi ----
    async def segna_traguardi(self, guild_id: int, user_id: int, chiavi: list[str]) -> list[str]:
        """Salva i traguardi e restituisce solo quelli nuovi."""
        nuovi: list[str] = []
        for chiave in chiavi:
            riga = await self._pool.fetchrow(
                "INSERT INTO progress_traguardi (guild_id, user_id, chiave) VALUES ($1, $2, $3) "
                "ON CONFLICT DO NOTHING RETURNING chiave",
                guild_id, user_id, chiave,
            )
            if riga is not None:
                nuovi.append(chiave)
        return nuovi

    async def traguardi_di(self, guild_id: int, user_id: int) -> set[str]:
        righe = await self._pool.fetch(
            "SELECT chiave FROM progress_traguardi WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return {r["chiave"] for r in righe}

    # ---- stagione ----
    async def xp_del_mese(self, guild_id: int, user_id: int, mese: str) -> int:
        valore = await self._pool.fetchval(
            "SELECT xp FROM leveling_activity WHERE guild_id = $1 AND user_id = $2 AND period_key = $3",
            guild_id, user_id, mese,
        )
        return int(valore or 0)

    async def gradini_riscattati(self, guild_id: int, user_id: int, stagione: str) -> int:
        valore = await self._pool.fetchval(
            "SELECT riscattati FROM progress_stagione WHERE guild_id = $1 AND user_id = $2 AND stagione = $3",
            guild_id, user_id, stagione,
        )
        return int(valore or 0)

    async def riscatta_gradini(
        self, guild_id: int, user_id: int, stagione: str, fino_a: int, monete_per: callable
    ) -> tuple[int, int] | None:
        """
        Porta i gradini riscattati a `fino_a` e paga (`monete_per(prima, fino_a)`) nella stessa
        transazione. Restituisce (gradini nuovi, monete), o None se non c'era niente di nuovo.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO progress_stagione (guild_id, user_id, stagione) VALUES ($1, $2, $3) "
                    "ON CONFLICT DO NOTHING",
                    guild_id, user_id, stagione,
                )
                prima = await conn.fetchval(
                    "SELECT riscattati FROM progress_stagione "
                    "WHERE guild_id = $1 AND user_id = $2 AND stagione = $3 FOR UPDATE",
                    guild_id, user_id, stagione,
                )
                if fino_a <= prima:
                    return None
                await conn.execute(
                    "UPDATE progress_stagione SET riscattati = $4 "
                    "WHERE guild_id = $1 AND user_id = $2 AND stagione = $3",
                    guild_id, user_id, stagione, fino_a,
                )
                monete = monete_per(prima, fino_a)
                await add_coins_in(conn, guild_id, user_id, monete)
        return fino_a - prima, monete

    async def stagioni_complete(self, guild_id: int, user_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM progress_stagione WHERE guild_id = $1 AND user_id = $2 AND riscattati >= $3",
            guild_id, user_id, STAGIONE_GRADINI,
        )

    # ---- profilo globale (solo numeri positivi, solo i propri) ----
    async def profilo_globale(self, user_id: int) -> tuple[int, int, int, int]:
        """(server con un livello, livello massimo, serie record, traguardi diversi)."""
        livelli = await self._pool.fetchrow(
            "SELECT count(*) AS n, COALESCE(max(level), 0) AS massimo FROM leveling_totals "
            "WHERE user_id = $1 AND xp_total > 0",
            user_id,
        )
        record = await self._pool.fetchval(
            "SELECT COALESCE(max(record), 0) FROM progress_serie WHERE user_id = $1", user_id
        )
        traguardi = await self._pool.fetchval(
            "SELECT count(DISTINCT chiave) FROM progress_traguardi WHERE user_id = $1", user_id
        )
        return livelli["n"], livelli["massimo"], record, traguardi
