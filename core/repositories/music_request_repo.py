"""
core/repositories/music_request_repo.py
=======================================
Tabella music_request_channels: il canale delle richieste di ogni server,
il messaggio player e la sessione (canale vocale) che mostra.
Funzioni coperte: SPEC §23 (NF-19)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class CanaleRichieste:
    guild_id: int
    channel_id: int
    message_id: int | None
    voice_channel_id: int | None


def _da_riga(riga) -> CanaleRichieste:
    return CanaleRichieste(
        guild_id=riga["guild_id"],
        channel_id=riga["channel_id"],
        message_id=riga["message_id"],
        voice_channel_id=riga["voice_channel_id"],
    )


class MusicRequestRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def set_channel(self, guild_id: int, channel_id: int, message_id: int, set_by: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO music_request_channels (guild_id, channel_id, message_id, set_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id) DO UPDATE
               SET channel_id = $2, message_id = $3, set_by = $4,
                   voice_channel_id = NULL, updated_at = now()
            """,
            guild_id, channel_id, message_id, set_by,
        )

    async def get(self, guild_id: int) -> CanaleRichieste | None:
        riga = await self._pool.fetchrow(
            "SELECT * FROM music_request_channels WHERE guild_id = $1", guild_id
        )
        return _da_riga(riga) if riga else None

    async def list_all(self) -> list[CanaleRichieste]:
        """Tutti i canali configurati: si leggono una volta all'avvio del cog."""
        righe = await self._pool.fetch("SELECT * FROM music_request_channels")
        return [_da_riga(r) for r in righe]

    async def set_voice_channel(self, guild_id: int, voice_channel_id: int) -> None:
        await self._pool.execute(
            "UPDATE music_request_channels SET voice_channel_id = $2, updated_at = now() "
            "WHERE guild_id = $1",
            guild_id, voice_channel_id,
        )

    async def set_message(self, guild_id: int, message_id: int) -> None:
        """Il messaggio player è stato cancellato a mano: se ne è mandato uno nuovo."""
        await self._pool.execute(
            "UPDATE music_request_channels SET message_id = $2, updated_at = now() WHERE guild_id = $1",
            guild_id, message_id,
        )

    async def remove(self, guild_id: int) -> CanaleRichieste | None:
        riga = await self._pool.fetchrow(
            "DELETE FROM music_request_channels WHERE guild_id = $1 RETURNING *", guild_id
        )
        return _da_riga(riga) if riga else None


def _get_pool():
    from core.database import db
    return db.pool


music_request_repo = MusicRequestRepository(pool_provider=_get_pool)
