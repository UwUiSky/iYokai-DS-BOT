"""
core/repositories/sondaggi_nativi_repo.py
=========================================
Sondaggi nativi di Discord seguiti dal bot: quelli programmati (si pubblicano più tardi) e quelli che si chiudono a N voti.
Apertura e conteggio girano sotto un blocco per sondaggio: un solo vincitore, mai due pubblicazioni o due chiusure.
Tabella: core/migrations/0560_sondaggi_nativi.sql.
Funzioni coperte: catalogo #128 UTL-090, 092 (D69, B23)
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

_COLONNE = ("id, guild_id, channel_id, message_id, autore_id, domanda, opzioni, multipla, durata_ore, discussione, "
            "chiudi_a_voti, voti, inizia_il, stato")


class SondaggiNativiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def crea(self, guild_id: int, channel_id: int, autore_id: int, domanda: str, opzioni: list[str], *,
                   multipla: bool = False, durata_ore: int = 24, discussione: bool = False, chiudi_a_voti: int | None = None,
                   inizia_il: datetime | None = None, stato: str = "programmato") -> int:
        return await self._pool.fetchval(
            "INSERT INTO sondaggi_nativi (guild_id, channel_id, autore_id, domanda, opzioni, multipla, durata_ore, discussione, "
            "chiudi_a_voti, inizia_il, stato) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING id",
            guild_id, channel_id, autore_id, domanda, opzioni, multipla, durata_ore, discussione, chiudi_a_voti, inizia_il, stato,
        )

    async def prendi(self, nativo_id: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow(f"SELECT {_COLONNE} FROM sondaggi_nativi WHERE id = $1", nativo_id)

    async def apri(self, nativo_id: int) -> asyncpg.Record | None:
        """Da «programmato» ad «aperto», una volta sola. Torna la riga (per pubblicarla) o None se non spetta più."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('sondaggio_nativo'), $1)", nativo_id % 2**31)
            return await conn.fetchrow(
                f"UPDATE sondaggi_nativi SET stato = 'aperto' WHERE id = $1 AND stato = 'programmato' RETURNING {_COLONNE}", nativo_id)

    async def imposta_messaggio(self, nativo_id: int, message_id: int) -> None:
        await self._pool.execute("UPDATE sondaggi_nativi SET message_id = $2 WHERE id = $1", nativo_id, message_id)

    async def conta_voto(self, message_id: int, delta: int) -> tuple[int, bool] | None:
        """Somma +1 o -1 ai voti del messaggio. Torna (id, da_chiudere): da_chiudere è vero per un solo chiamante, quando
        si arriva alla soglia. None se il messaggio non ha soglia o è già chiuso."""
        async with self._pool.acquire() as conn, conn.transaction():
            nid = await conn.fetchval(
                "SELECT id FROM sondaggi_nativi WHERE message_id = $1 AND stato = 'aperto' AND chiudi_a_voti IS NOT NULL", message_id)
            if nid is None:
                return None
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('sondaggio_nativo'), $1)", nid % 2**31)
            r = await conn.fetchrow(
                "UPDATE sondaggi_nativi SET voti = GREATEST(0, voti + $2) WHERE id = $1 AND stato = 'aperto' "
                "RETURNING voti, chiudi_a_voti", nid, delta)
            if r is None:
                return None
            if delta > 0 and r["voti"] >= r["chiudi_a_voti"]:
                await conn.execute("UPDATE sondaggi_nativi SET stato = 'chiuso' WHERE id = $1", nid)
                return nid, True
        return nid, False

    async def elimina(self, nativo_id: int) -> None:
        await self._pool.execute("DELETE FROM sondaggi_nativi WHERE id = $1", nativo_id)

    async def elimina_del_canale(self, guild_id: int, channel_id: int) -> int:
        r = await self._pool.execute("DELETE FROM sondaggi_nativi WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id)
        return int(r.split()[-1])


def _get_pool():
    from core.database import db

    return db.pool


sondaggi_nativi_repo = SondaggiNativiRepository(pool_provider=_get_pool)
