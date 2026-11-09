"""
core/repositories/embed_bottoni_repo.py
=======================================
Bottoni degli embed salvati: link o «mostra tag», massimo 25 per embed (5 righe da 5). Si cancellano con
l'embed (chiave esterna). Tabella: core/migrations/0542_embed_avanzati.sql.
Funzioni coperte: catalogo #128 UTL-080 (D69, B4)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

MAX_BOTTONI = 25


@dataclass(frozen=True)
class BottoneEmbed:
    posizione: int
    tipo: str
    etichetta: str
    valore: str


class EmbedBottoniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def elenco(self, guild_id: int, embed: str) -> list[BottoneEmbed]:
        righe = await self._pool.fetch(
            "SELECT posizione, tipo, etichetta, valore FROM embed_bottoni "
            "WHERE guild_id = $1 AND embed = $2 ORDER BY posizione",
            guild_id, embed.lower(),
        )
        return [BottoneEmbed(r["posizione"], r["tipo"], r["etichetta"], r["valore"]) for r in righe]

    async def prendi(self, guild_id: int, embed: str, posizione: int) -> BottoneEmbed | None:
        r = await self._pool.fetchrow(
            "SELECT posizione, tipo, etichetta, valore FROM embed_bottoni "
            "WHERE guild_id = $1 AND embed = $2 AND posizione = $3",
            guild_id, embed.lower(), posizione,
        )
        return BottoneEmbed(r["posizione"], r["tipo"], r["etichetta"], r["valore"]) if r else None

    async def aggiungi(self, guild_id: int, embed: str, tipo: str, etichetta: str, valore: str) -> str:
        """"ok", "pieno" (25) o "senza_embed"."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1, hashtext($2))", guild_id % 2**31, embed.lower())
            if not await conn.fetchval("SELECT 1 FROM saved_embeds WHERE guild_id = $1 AND name = $2", guild_id, embed.lower()):
                return "senza_embed"
            n = await conn.fetchval("SELECT count(*) FROM embed_bottoni WHERE guild_id = $1 AND embed = $2", guild_id, embed.lower())
            if n >= MAX_BOTTONI:
                return "pieno"
            await conn.execute(
                "INSERT INTO embed_bottoni (guild_id, embed, posizione, tipo, etichetta, valore) VALUES ($1, $2, $3, $4, $5, $6)",
                guild_id, embed.lower(), n, tipo, etichetta, valore,
            )
            return "ok"

    async def togli(self, guild_id: int, embed: str, posizione: int) -> bool:
        """Toglie il bottone e fa scalare i successivi."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1, hashtext($2))", guild_id % 2**31, embed.lower())
            tolto = await conn.fetchval(
                "DELETE FROM embed_bottoni WHERE guild_id = $1 AND embed = $2 AND posizione = $3 RETURNING 1",
                guild_id, embed.lower(), posizione,
            )
            if tolto:
                await conn.execute(
                    "UPDATE embed_bottoni SET posizione = posizione - 1 "
                    "WHERE guild_id = $1 AND embed = $2 AND posizione > $3",
                    guild_id, embed.lower(), posizione,
                )
            return bool(tolto)


def _get_pool():
    from core.database import db

    return db.pool


embed_bottoni_repo = EmbedBottoniRepository(pool_provider=_get_pool)
