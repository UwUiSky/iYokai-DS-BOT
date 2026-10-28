"""
core/repositories/invite_links_repo.py
======================================
Link d'invito personali (r10). Tabella: core/migrations/0380_inviti_link_personali.sql.
Funzioni coperte: SPEC §23 (NF-27, link personali r10)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class LinkPersonale:
    slug: str
    guild_id: int
    user_id: int
    discord_code: str | None
    created_at: datetime
    last_used_at: datetime | None = None


def _link(r) -> LinkPersonale | None:
    if r is None:
        return None
    return LinkPersonale(r["slug"], r["guild_id"], r["user_id"], r["discord_code"], r["created_at"], r["last_used_at"])


class InviteLinksRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def crea(self, slug: str, guild_id: int, user_id: int) -> LinkPersonale | None:
        """None se lo slug è già preso (da chiunque). Se il membro ha già un link, resta quello."""
        esistente = await self.del_membro(guild_id, user_id)
        if esistente is not None:
            return esistente
        r = await self._pool.fetchrow(
            "INSERT INTO invite_personal_links (slug, guild_id, user_id) VALUES ($1, $2, $3) "
            "ON CONFLICT DO NOTHING RETURNING *",
            slug, guild_id, user_id,
        )
        if r is None:  # slug preso da un altro, oppure due richieste dello stesso membro insieme
            return await self.del_membro(guild_id, user_id)
        return _link(r)

    async def da_slug(self, slug: str) -> LinkPersonale | None:
        return _link(await self._pool.fetchrow("SELECT * FROM invite_personal_links WHERE slug = $1", slug))

    async def del_membro(self, guild_id: int, user_id: int) -> LinkPersonale | None:
        return _link(await self._pool.fetchrow(
            "SELECT * FROM invite_personal_links WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        ))

    async def da_codice(self, guild_id: int, codice: str) -> LinkPersonale | None:
        return _link(await self._pool.fetchrow(
            "SELECT * FROM invite_personal_links WHERE guild_id = $1 AND discord_code = $2", guild_id, codice
        ))

    async def dell_utente(self, user_id: int) -> list[LinkPersonale]:
        righe = await self._pool.fetch(
            "SELECT * FROM invite_personal_links WHERE user_id = $1 ORDER BY guild_id", user_id
        )
        return [_link(r) for r in righe]

    async def imposta_codice(self, slug: str, codice: str | None) -> None:
        await self._pool.execute("UPDATE invite_personal_links SET discord_code = $2 WHERE slug = $1", slug, codice)

    async def segna_uso(self, slug: str) -> None:
        await self._pool.execute("UPDATE invite_personal_links SET last_used_at = now() WHERE slug = $1", slug)

    async def elimina_del_membro(self, guild_id: int, user_id: int) -> str | None:
        """Toglie il link e restituisce il codice Discord da cancellare (se c'era)."""
        r = await self._pool.fetchrow(
            "DELETE FROM invite_personal_links WHERE guild_id = $1 AND user_id = $2 RETURNING discord_code",
            guild_id, user_id,
        )
        return r["discord_code"] if r else None


def _get_pool():
    from core.database import db
    return db.pool


invite_links_repo = InviteLinksRepository(pool_provider=_get_pool)
