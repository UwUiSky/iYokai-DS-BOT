"""
core/repositories/quiz_repo.py
==============================
Regole del quiz di ogni server (`quiz_impostazioni`) e domande caricate dal server (`quiz_domande_server`).
Il tetto di 300 domande è controllato dentro la stessa transazione che scrive, con un blocco per server.
Tabelle: core/migrations/0572_fun_impostazioni.sql, 0573_quiz_domande_server.sql.
Funzioni coperte: SPEC §16 (FUN-005, 006; #131)
"""

from __future__ import annotations

import json

import asyncpg

from core.quiz_logic import MAX_DOMANDE_SERVER, Domanda, RegoleQuiz


class QuizRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def regole(self, guild_id: int) -> RegoleQuiz:
        r = await self._pool.fetchrow(
            "SELECT punti, secondi, mostra_risposta, bot_gioca FROM quiz_impostazioni WHERE guild_id = $1", guild_id
        )
        return RegoleQuiz(**dict(r)) if r else RegoleQuiz()

    async def imposta_regole(
        self, guild_id: int, punti: int | None, secondi: int | None, mostra: bool | None, bot: bool | None
    ) -> RegoleQuiz:
        """Cambia solo i campi dati (gli altri restano) con una sola istruzione."""
        r = await self._pool.fetchrow(
            "INSERT INTO quiz_impostazioni (guild_id, punti, secondi, mostra_risposta, bot_gioca) "
            "VALUES ($1, COALESCE($2, 10), COALESCE($3, 30), COALESCE($4, TRUE), COALESCE($5, FALSE)) "
            "ON CONFLICT (guild_id) DO UPDATE SET punti = COALESCE($2, quiz_impostazioni.punti), "
            "secondi = COALESCE($3, quiz_impostazioni.secondi), "
            "mostra_risposta = COALESCE($4, quiz_impostazioni.mostra_risposta), "
            "bot_gioca = COALESCE($5, quiz_impostazioni.bot_gioca) "
            "RETURNING punti, secondi, mostra_risposta, bot_gioca",
            guild_id, punti, secondi, mostra, bot,
        )
        return RegoleQuiz(**dict(r))

    async def aggiungi(self, guild_id: int, autore_id: int, domande: list[Domanda]) -> bool:
        """Salva tutte le domande o nessuna: falso se si supererebbe il tetto del server."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(7131, $1::int)", guild_id % 2_000_000_000)
            presenti = await conn.fetchval("SELECT count(*) FROM quiz_domande_server WHERE guild_id = $1", guild_id)
            if presenti + len(domande) > MAX_DOMANDE_SERVER:
                return False
            await conn.executemany(
                "INSERT INTO quiz_domande_server (guild_id, tema, domanda, risposte, autore_id) VALUES ($1, $2, $3, $4::jsonb, $5)",
                [(guild_id, d.tema, d.testo, json.dumps(list(d.risposte)), autore_id) for d in domande],
            )
            return True

    async def elenco(self, guild_id: int) -> list[tuple[int, str, str]]:
        righe = await self._pool.fetch(
            "SELECT id, tema, domanda FROM quiz_domande_server WHERE guild_id = $1 ORDER BY id LIMIT $2",
            guild_id, MAX_DOMANDE_SERVER,
        )
        return [(r["id"], r["tema"], r["domanda"]) for r in righe]

    async def domande(self, guild_id: int) -> list[Domanda]:
        righe = await self._pool.fetch(
            "SELECT tema, domanda, risposte FROM quiz_domande_server WHERE guild_id = $1 ORDER BY id LIMIT $2",
            guild_id, MAX_DOMANDE_SERVER,
        )
        return [Domanda(r["domanda"], tuple(json.loads(r["risposte"])), r["tema"]) for r in righe]

    async def rimuovi(self, guild_id: int, domanda_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM quiz_domande_server WHERE guild_id = $1 AND id = $2", guild_id, domanda_id
        )
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


quiz_repo = QuizRepository(pool_provider=_get_pool)
