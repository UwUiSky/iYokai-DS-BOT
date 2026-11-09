"""
core/repositories/citazioni_repo.py
===================================
Citazioni del server (massimo 500) e conteggio dei comandi usati per server e giorno.
Tabelle: core/migrations/0555_citazioni_comandi.sql.
Funzioni coperte: catalogo #128 UTL-206, 207, 222 (D69, B16)
"""

from __future__ import annotations

from datetime import date

import asyncpg

from core.citazioni_logic import MAX_PER_SERVER, MAX_RISULTATI


class TroppeCitazioni(Exception):
    """Il server ha già 500 citazioni."""


class CitazioniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def conta(self, guild_id: int) -> int:
        return await self._pool.fetchval("SELECT count(*) FROM citazioni WHERE guild_id = $1", guild_id)

    async def aggiungi(self, guild_id: int, testo: str, autore_id: int | None, aggiunta_da: int, link: str | None) -> int:
        async with self._pool.acquire() as con, con.transaction():
            await con.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
            if await con.fetchval("SELECT count(*) FROM citazioni WHERE guild_id = $1", guild_id) >= MAX_PER_SERVER:
                raise TroppeCitazioni
            return await con.fetchval(
                "INSERT INTO citazioni (guild_id, testo, autore_id, aggiunta_da, link) VALUES ($1,$2,$3,$4,$5) RETURNING id",
                guild_id, testo, autore_id, aggiunta_da, link,
            )

    async def a_caso(self, guild_id: int) -> dict | None:
        r = await self._pool.fetchrow("SELECT * FROM citazioni WHERE guild_id = $1 ORDER BY random() LIMIT 1", guild_id)
        return dict(r) if r else None

    async def cerca(self, guild_id: int, testo: str) -> list[dict]:
        schema = testo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        righe = await self._pool.fetch(
            "SELECT * FROM citazioni WHERE guild_id = $1 AND testo ILIKE $2 ORDER BY id DESC LIMIT $3",
            guild_id, f"%{schema}%", MAX_RISULTATI,
        )
        return [dict(r) for r in righe]

    async def elimina(self, guild_id: int, numero: int, aggiunta_da: int) -> bool:
        """Elimina solo una citazione salvata da `aggiunta_da`."""
        stato = await self._pool.execute(
            "DELETE FROM citazioni WHERE guild_id = $1 AND id = $2 AND aggiunta_da = $3", guild_id, numero, aggiunta_da
        )
        return stato.endswith(" 1")

    async def tutte(self, guild_id: int) -> list[dict]:
        return [dict(r) for r in await self._pool.fetch("SELECT * FROM citazioni WHERE guild_id = $1 ORDER BY id", guild_id)]

    async def elimina_tutte(self, guild_id: int) -> int:
        return int((await self._pool.execute("DELETE FROM citazioni WHERE guild_id = $1", guild_id)).split()[-1])

    async def importa(self, guild_id: int, righe: list[dict], aggiunta_da: int) -> int:
        """Aggiunge le righe che stanno nei 500 posti. Ritorna quante ne ha messe."""
        aggiunte = 0
        for r in righe:
            try:
                await self.aggiungi(guild_id, r["testo"], r["autore_id"], aggiunta_da, r["link"])
            except TroppeCitazioni:
                break
            aggiunte += 1
        return aggiunte


class ComandiUsoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def registra(self, guild_id: int, comando: str, giorno: date) -> None:
        await self._pool.execute(
            "INSERT INTO comandi_uso_server (guild_id, comando, giorno, usi) VALUES ($1,$2,$3,1) "
            "ON CONFLICT (guild_id, giorno, comando) DO UPDATE SET usi = comandi_uso_server.usi + 1",
            guild_id, comando[:100], giorno,
        )

    async def piu_usati(self, guild_id: int, dal: date, limite: int = 10) -> list[tuple[str, int]]:
        righe = await self._pool.fetch(
            "SELECT comando, sum(usi)::int AS n FROM comandi_uso_server WHERE guild_id = $1 AND giorno >= $2 "
            "GROUP BY comando ORDER BY n DESC, comando LIMIT $3", guild_id, dal, limite,
        )
        return [(r["comando"], r["n"]) for r in righe]


def _get_pool():
    from core.database import db

    return db.pool


citazioni_repo = CitazioniRepository(pool_provider=_get_pool)
comandi_uso_repo = ComandiUsoRepository(pool_provider=_get_pool)
