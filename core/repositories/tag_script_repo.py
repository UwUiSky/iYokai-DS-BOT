"""
core/repositories/tag_script_repo.py
====================================
Dati per server degli script dei tag (`{dati:...}`, tetto di chiavi sotto blocco per server) e ultimi errori degli script
(10 per tag). Tabelle: core/migrations/0562_tag_dati_errori.sql.
Funzioni coperte: catalogo #128 UTL-032, UTL-043 (D69, B26)
"""

from __future__ import annotations

import logging

import asyncpg

from core.repositories.tetto_server import tetto_per_server

logger = logging.getLogger("iyokai.tag_script")
ERRORI_PER_TAG = 10


async def massimo_chiavi(guild_id: int, bot=None) -> int:
    """Chiavi di dati per server: 1.000, di più con il Premium (si legge solo quando serve scrivere)."""
    from core.premium import guild_has_premium_access
    from core.tag_script_logic import MAX_CHIAVI, MAX_CHIAVI_PREMIUM

    try:
        premium = await guild_has_premium_access(guild_id, "custom_commands", bot)
    except Exception:
        logger.warning("Premium non letto per il server %s.", guild_id, exc_info=True)
        premium = False
    return MAX_CHIAVI_PREMIUM if premium else MAX_CHIAVI


class _ArchivioServer:
    """L'interfaccia che il motore si aspetta (get, set, delete), legata a un server."""

    def __init__(self, repo: "TagScriptRepository", guild_id: int, massimo, autore: int | None = None,
                 massimo_autore: int | None = None) -> None:
        self._repo, self._guild_id, self._massimo = repo, guild_id, massimo
        self._autore, self._massimo_autore = autore, massimo_autore

    async def get(self, chiave: str) -> str | None:
        return await self._repo.leggi_dato(self._guild_id, chiave)

    async def set(self, chiave: str, valore: str) -> None:
        from core.tag_script_logic import ErroreScript

        massimo = self._massimo if isinstance(self._massimo, int) else await self._massimo()
        if await self._repo.imposta_dato(
                self._guild_id, chiave, valore, massimo=massimo, autore=self._autore, massimo_autore=self._massimo_autore) == "pieno":
            raise ErroreScript("tag_script_dati_pieni")

    async def delete(self, chiave: str) -> None:
        await self._repo.togli_dato(self._guild_id, chiave)


class TagScriptRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def archivio(self, guild_id: int, massimo, autore: int | None = None, massimo_autore: int | None = None) -> _ArchivioServer:
        return _ArchivioServer(self, guild_id, massimo, autore, massimo_autore)

    async def leggi_dato(self, guild_id: int, chiave: str) -> str | None:
        return await self._pool.fetchval("SELECT valore FROM tag_dati WHERE guild_id = $1 AND chiave = $2", guild_id, chiave)

    async def imposta_dato(self, guild_id: int, chiave: str, valore: str, *, massimo: int, autore: int | None = None,
                           massimo_autore: int | None = None) -> str:
        """"ok" o "pieno" (chiavi nuove oltre il tetto del server o di chi scrive). Riscrivere una chiave che c'è non conta."""
        async with tetto_per_server(self._pool, "tag_dati", guild_id) as conn:
            esiste = await conn.fetchval("SELECT 1 FROM tag_dati WHERE guild_id = $1 AND chiave = $2", guild_id, chiave)
            if not esiste and await conn.fetchval("SELECT count(*) FROM tag_dati WHERE guild_id = $1", guild_id) >= massimo:
                return "pieno"
            if (not esiste and autore is not None and massimo_autore is not None
                    and await conn.fetchval("SELECT count(*) FROM tag_dati WHERE guild_id = $1 AND autore = $2", guild_id, autore) >= massimo_autore):
                return "pieno"
            await conn.execute(
                "INSERT INTO tag_dati (guild_id, chiave, valore, autore) VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (guild_id, chiave) DO UPDATE SET valore = EXCLUDED.valore, aggiornato = NOW()",
                guild_id, chiave, valore, autore)
        return "ok"

    async def togli_dato(self, guild_id: int, chiave: str) -> None:
        await self._pool.execute("DELETE FROM tag_dati WHERE guild_id = $1 AND chiave = $2", guild_id, chiave)

    async def registra_errore(self, guild_id: int, tag: str, chiave: str, dettaglio: str) -> None:
        """Salva l'errore e tiene solo gli ultimi 10 di quel tag."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("INSERT INTO tag_errori (guild_id, tag, chiave, dettaglio) VALUES ($1, $2, $3, $4)",
                               guild_id, tag, chiave, dettaglio[:100])
            await conn.execute(
                "DELETE FROM tag_errori WHERE guild_id = $1 AND tag = $2 AND id NOT IN "
                "(SELECT id FROM tag_errori WHERE guild_id = $1 AND tag = $2 ORDER BY id DESC LIMIT $3)",
                guild_id, tag, ERRORI_PER_TAG)

    async def ultimi_errori(self, guild_id: int, tag: str) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT chiave, dettaglio, creato_il FROM tag_errori WHERE guild_id = $1 AND tag = $2 ORDER BY id DESC LIMIT $3",
            guild_id, tag, ERRORI_PER_TAG)

    async def togli_errori(self, guild_id: int, tag: str) -> None:
        await self._pool.execute("DELETE FROM tag_errori WHERE guild_id = $1 AND tag = $2", guild_id, tag)


def _get_pool():
    from core.database import db

    return db.pool


tag_script_repo = TagScriptRepository(pool_provider=_get_pool)
