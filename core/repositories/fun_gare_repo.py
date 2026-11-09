"""
core/repositories/fun_gare_repo.py
==================================
Punteggi delle gare di /giochi (dado, spinner) in `fun_punteggi` e mazzo di carte di ogni server in `fun_mazzi`.
Ogni scrittura è una sola istruzione condizionata: due clic insieme non contano due volte.
Tabelle: core/migrations/0571_fun_punteggi.sql.
Funzioni coperte: SPEC §16 (FUN-003, 015, 016, 018; #131)
"""

from __future__ import annotations

import random

import asyncpg

from core.fun_gare_logic import SPINNER_ATTESA_SECONDI, TOP, nuovo_mazzo, pesca_dal_mazzo, restanti


class FunGareRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def prova_dado(self, guild_id: int, user_id: int, periodo: str, valore: int) -> int | None:
        """Registra il tiro del giorno. Restituisce il valore appena tirato, None se ha già tirato oggi."""
        return await self._pool.fetchval(
            "INSERT INTO fun_punteggi (guild_id, gara, periodo, user_id, valore) VALUES ($1, 'dado', $2, $3, $4) "
            "ON CONFLICT DO NOTHING RETURNING valore",
            guild_id, periodo, user_id, valore,
        )

    async def tiro_del_giorno(self, guild_id: int, user_id: int, periodo: str) -> int | None:
        return await self._pool.fetchval(
            "SELECT valore FROM fun_punteggi WHERE guild_id = $1 AND gara = 'dado' AND periodo = $2 AND user_id = $3",
            guild_id, periodo, user_id,
        )

    async def registra_giro(self, guild_id: int, user_id: int, periodo: str, secondi: int) -> bool:
        """
        Un giro ogni ora: vero se il giro parte (e tiene il record della settimana), falso se è troppo presto.
        L'attesa è controllata nella stessa istruzione che scrive (sull'ultimo giro di qualsiasi settimana).
        """
        riga = await self._pool.fetchval(
            "WITH recente AS (SELECT 1 FROM fun_punteggi WHERE guild_id = $1 AND gara = 'spinner' AND user_id = $2 "
            "AND aggiornato > now() - make_interval(secs => $5)) "
            "INSERT INTO fun_punteggi (guild_id, gara, periodo, user_id, valore) "
            "SELECT $1, 'spinner', $3, $2, $4 WHERE NOT EXISTS (SELECT 1 FROM recente) "
            "ON CONFLICT (guild_id, gara, periodo, user_id) DO UPDATE SET valore = GREATEST(fun_punteggi.valore, EXCLUDED.valore), "
            "aggiornato = now() WHERE fun_punteggi.aggiornato <= now() - make_interval(secs => $5) RETURNING 1",
            guild_id, user_id, periodo, secondi, float(SPINNER_ATTESA_SECONDI),
        )
        return bool(riga)

    async def aggiungi_punti(self, guild_id: int, gara: str, periodo: str, user_id: int, punti: int) -> int:
        """Somma `punti` al punteggio con una sola istruzione (niente lettura prima). Restituisce il totale."""
        return await self._pool.fetchval(
            "INSERT INTO fun_punteggi (guild_id, gara, periodo, user_id, valore) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (guild_id, gara, periodo, user_id) DO UPDATE SET valore = fun_punteggi.valore + EXCLUDED.valore, "
            "aggiornato = now() RETURNING valore",
            guild_id, gara, periodo, user_id, punti,
        )

    async def classifica(self, guild_id: int, gara: str, periodo: str) -> list[tuple[int, int]]:
        righe = await self._pool.fetch(
            "SELECT user_id, valore FROM fun_punteggi WHERE guild_id = $1 AND gara = $2 AND periodo = $3 "
            "ORDER BY valore DESC, aggiornato, user_id LIMIT $4",
            guild_id, gara, periodo, TOP,
        )
        return [(r["user_id"], r["valore"]) for r in righe]

    async def classifica_sempre(self, guild_id: int, gara: str) -> list[tuple[int, int]]:
        """Somma di tutti i periodi (per il dado: i punti di ogni tiro giornaliero)."""
        righe = await self._pool.fetch(
            "SELECT user_id, sum(valore)::bigint AS totale FROM fun_punteggi WHERE guild_id = $1 AND gara = $2 "
            "GROUP BY user_id ORDER BY totale DESC, user_id LIMIT $3",
            guild_id, gara, TOP,
        )
        return [(r["user_id"], r["totale"]) for r in righe]

    async def azzera(self, guild_id: int, gara: str | None) -> int:
        """Cancella i punteggi di una gara (None = tutte). Restituisce quante righe."""
        esito = await self._pool.execute(
            "DELETE FROM fun_punteggi WHERE guild_id = $1 AND ($2::text IS NULL OR gara = $2)", guild_id, gara
        )
        return int(esito.split()[-1])

    async def pesca(self, guild_id: int, quante: int, rng: random.Random) -> tuple[list[str], int]:
        """Pesca dal mazzo del server (lo crea se manca) dentro una transazione. Restituisce (carte, restanti)."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO fun_mazzi (guild_id, rimaste) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                guild_id, nuovo_mazzo(rng),
            )
            rimaste = await conn.fetchval("SELECT rimaste FROM fun_mazzi WHERE guild_id = $1 FOR UPDATE", guild_id)
            carte, resto = pesca_dal_mazzo(rimaste, quante)
            if carte:
                await conn.execute("UPDATE fun_mazzi SET rimaste = $2 WHERE guild_id = $1", guild_id, resto)
            return carte, restanti(resto)

    async def rimescola(self, guild_id: int, rng: random.Random) -> None:
        await self._pool.execute(
            "INSERT INTO fun_mazzi (guild_id, rimaste) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET rimaste = EXCLUDED.rimaste, mescolato_il = now()",
            guild_id, nuovo_mazzo(rng),
        )

    async def carte_restanti(self, guild_id: int) -> int:
        rimaste = await self._pool.fetchval("SELECT rimaste FROM fun_mazzi WHERE guild_id = $1", guild_id)
        return 52 if rimaste is None else restanti(rimaste)


def _get_pool():
    from core.database import db

    return db.pool


fun_gare_repo = FunGareRepository(pool_provider=_get_pool)
