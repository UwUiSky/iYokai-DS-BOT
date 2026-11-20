"""
core/repositories/music_generi_repo.py
======================================
Tabella music_genere_playlist (MUS-014): le playlist per genere scelte dall'owner. I tetti si controllano
sotto un lock, nella stessa transazione della scrittura.
Funzioni coperte: SPEC §9 (catalogo MUS-014)
"""

from __future__ import annotations

import asyncpg

from core.music_generi_logic import MAX_GENERI, MAX_PLAYLIST_PER_GENERE, MAX_TOTALE, VoceGenere


class MusicGeneriRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def elenco(self) -> list[VoceGenere]:
        righe = await self._pool.fetch(
            "SELECT genere, titolo, link FROM music_genere_playlist ORDER BY lower(genere), lower(titolo) LIMIT $1",
            MAX_TOTALE,
        )
        return [VoceGenere(r["genere"], r["titolo"], r["link"]) for r in righe]

    async def aggiungi(self, genere: str, titolo: str, link: str, owner_id: int) -> str:
        """«ok», «gia», «pieno_generi», «pieno_genere» o «pieno_totale»."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(7170014)")
                if await conn.fetchval(
                    "SELECT 1 FROM music_genere_playlist WHERE lower(genere) = lower($1) "
                    "AND (lower(titolo) = lower($2) OR link = $3)", genere, titolo, link,
                ):
                    return "gia"
                if await conn.fetchval("SELECT count(*) FROM music_genere_playlist") >= MAX_TOTALE:
                    return "pieno_totale"
                nel_genere = await conn.fetchval(
                    "SELECT count(*) FROM music_genere_playlist WHERE lower(genere) = lower($1)", genere
                )
                if nel_genere == 0:
                    if await conn.fetchval("SELECT count(DISTINCT lower(genere)) FROM music_genere_playlist") >= MAX_GENERI:
                        return "pieno_generi"
                elif nel_genere >= MAX_PLAYLIST_PER_GENERE:
                    return "pieno_genere"
                await conn.execute(
                    "INSERT INTO music_genere_playlist (genere, titolo, link, aggiunta_da) VALUES ($1, $2, $3, $4)",
                    genere, titolo, link, owner_id,
                )
                return "ok"

    async def togli(self, genere: str, titolo: str | None) -> int:
        """Toglie una playlist, o tutto il genere se `titolo` e' vuoto. Quante righe sono sparite."""
        if titolo:
            esito = await self._pool.execute(
                "DELETE FROM music_genere_playlist WHERE lower(genere) = lower($1) AND lower(titolo) = lower($2)",
                genere, titolo,
            )
        else:
            esito = await self._pool.execute("DELETE FROM music_genere_playlist WHERE lower(genere) = lower($1)", genere)
        return int(esito.split()[-1])


def _get_pool():
    from core.database import db
    return db.pool


music_generi_repo = MusicGeneriRepository(pool_provider=_get_pool)
