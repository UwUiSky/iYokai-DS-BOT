"""
core/repositories/saved_embed_repo.py
=====================================
Embed salvati per server (NF-17). Tabella: core/migrations/0086_saved_embeds.sql.
I nomi sono salvati in minuscolo: "Annuncio" e "annuncio" sono lo stesso embed.
Funzioni coperte: SPEC §22 (NF-17)
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import asyncpg

from core.embed_builder_logic import MAX_EMBED


@dataclass(frozen=True)
class SavedEmbed:
    guild_id: int
    name: str
    data: dict
    channel_id: int | None
    message_id: int | None


def _riga(r) -> SavedEmbed:
    dati = r["data"]
    return SavedEmbed(
        guild_id=r["guild_id"],
        name=r["name"],
        data=json.loads(dati) if isinstance(dati, str) else dati,
        channel_id=r["channel_id"],
        message_id=r["message_id"],
    )


_COLONNE = "guild_id, name, data, channel_id, message_id"


class SavedEmbedRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def create(self, guild_id: int, name: str, data_json: str, created_by: int) -> str:
        """"ok", "esiste" o "pieno" (tetto per server); tetto e scrittura nella stessa query."""
        nome = name.lower()
        riga = await self._pool.fetchrow(
            """
            INSERT INTO saved_embeds (guild_id, name, data, created_by)
            SELECT $1, $2, $3::jsonb, $4
            WHERE (SELECT count(*) FROM saved_embeds WHERE guild_id = $1) < $5
            ON CONFLICT (guild_id, name) DO NOTHING
            RETURNING name
            """,
            guild_id, nome, data_json, created_by, MAX_EMBED,
        )
        if riga is not None:
            return "ok"
        esiste = await self._pool.fetchval(
            "SELECT 1 FROM saved_embeds WHERE guild_id = $1 AND name = $2", guild_id, nome
        )
        return "esiste" if esiste else "pieno"

    async def get(self, guild_id: int, name: str) -> SavedEmbed | None:
        r = await self._pool.fetchrow(
            f"SELECT {_COLONNE} FROM saved_embeds WHERE guild_id = $1 AND name = $2", guild_id, name.lower()
        )
        return None if r is None else _riga(r)

    async def list(self, guild_id: int) -> list[SavedEmbed]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM saved_embeds WHERE guild_id = $1 ORDER BY name", guild_id
        )
        return [_riga(r) for r in righe]

    async def update_data(self, guild_id: int, name: str, data_json: str) -> bool:
        esito = await self._pool.execute(
            "UPDATE saved_embeds SET data = $3::jsonb, updated_at = now() WHERE guild_id = $1 AND name = $2",
            guild_id, name.lower(), data_json,
        )
        return esito.endswith(" 1")

    async def set_published(self, guild_id: int, name: str, channel_id: int | None, message_id: int | None) -> None:
        await self._pool.execute(
            "UPDATE saved_embeds SET channel_id = $3, message_id = $4 WHERE guild_id = $1 AND name = $2",
            guild_id, name.lower(), channel_id, message_id,
        )

    async def delete(self, guild_id: int, name: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM saved_embeds WHERE guild_id = $1 AND name = $2", guild_id, name.lower()
        )
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db
    return db.pool


saved_embed_repo = SavedEmbedRepository(pool_provider=_get_pool)
