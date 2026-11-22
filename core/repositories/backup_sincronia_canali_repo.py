"""
core/repositories/backup_sincronia_canali_repo.py
=================================================
Sincronia dei messaggi tra due canali, in una o in due direzioni: una riga per direzione
(canale d'origine -> webhook del canale di arrivo). Al massimo 10 direzioni per server.
Funzioni coperte: BKP-028
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_DIREZIONI_PER_SERVER = 10


@dataclass(frozen=True)
class DirezioneCanali:
    canale_da: int
    guild_da: int
    canale_a: int
    guild_a: int


class BackupSincroniaCanaliRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    async def attiva(
        self, canale_da: int, guild_da: int, canale_a: int, guild_a: int, webhook_url: str, created_by: int
    ) -> bool:
        """Crea o aggiorna una direzione. False se uno dei due server ha già 10 direzioni."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('backup_sincronia_canali'))")
            esiste = await conn.fetchval("SELECT 1 FROM backup_sincronia_canali WHERE canale_da = $1", canale_da)
            if not esiste:
                for g in {guild_da, guild_a}:
                    quante = await conn.fetchval(
                        "SELECT count(*) FROM backup_sincronia_canali WHERE guild_da = $1 OR guild_a = $1", g
                    )
                    if quante >= MAX_DIREZIONI_PER_SERVER:
                        return False
            await conn.execute(
                "INSERT INTO backup_sincronia_canali (canale_da, guild_da, canale_a, guild_a, webhook_url, created_by) "
                "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (canale_da) DO UPDATE SET "
                "canale_a = $3, guild_a = $4, webhook_url = $5, created_by = $6",
                canale_da, guild_da, canale_a, guild_a, webhook_url, created_by,
            )
        return True

    async def get_webhook_url(self, canale_id: int) -> str | None:
        """Per il dispatcher: dove va un messaggio scritto in questo canale."""
        return await self._pool.fetchval(
            "SELECT webhook_url FROM backup_sincronia_canali WHERE canale_da = $1", canale_id
        )

    async def togli_coppia(self, guild_id: int, canale_a: int, canale_b: int) -> int:
        """Toglie le direzioni tra i due canali (di un server dell'utente). Quante."""
        esito = await self._pool.execute(
            "DELETE FROM backup_sincronia_canali WHERE (guild_da = $1 OR guild_a = $1) AND "
            "((canale_da = $2 AND canale_a = $3) OR (canale_da = $3 AND canale_a = $2))",
            guild_id, canale_a, canale_b,
        )
        return int(esito.rsplit(" ", 1)[-1])

    async def elenco(self, guild_id: int) -> list[DirezioneCanali]:
        righe = await self._pool.fetch(
            "SELECT canale_da, guild_da, canale_a, guild_a FROM backup_sincronia_canali "
            "WHERE guild_da = $1 OR guild_a = $1 ORDER BY creato_il LIMIT $2",
            guild_id, MAX_DIREZIONI_PER_SERVER,
        )
        return [DirezioneCanali(**dict(r)) for r in righe]


def _get_pool():
    from core.database import db

    return db.pool


backup_sincronia_canali_repo = BackupSincroniaCanaliRepository(pool_provider=_get_pool)
