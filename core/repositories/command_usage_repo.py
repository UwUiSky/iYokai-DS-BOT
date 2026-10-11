"""
core/repositories/command_usage_repo.py
=======================================
Ultimo comando usato per server e utente (tabella `command_usage`,
migrazione 0022). Serve al pannello di -cerca-comando (issue #147).

Dato personale: una sola riga per (server, utente), conservata al massimo
`giorni` giorni e al massimo `tetto` righe in tutto. La pulizia parte da
sola ogni `ogni_n_scritture` scritture (e all'avvio, dal cog).
Cancellazione per utente/server: la farà il registro dei dati (F5, core/data_registry.py) con
`DELETE ... WHERE user_id = $1` / `guild_id = $1`.
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger("iyokai.command_usage")

GIORNI_CONSERVAZIONE = 90
TETTO_RIGHE = 200_000
OGNI_N_SCRITTURE = 500
MAX_PERCORSO = 100


class CommandUsageRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self.giorni = GIORNI_CONSERVAZIONE
        self.tetto = TETTO_RIGHE
        self.ogni_n_scritture = OGNI_N_SCRITTURE
        self._scritture = 0

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def registra(self, guild_id: int | None, user_id: int, percorso: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO command_usage (guild_id, user_id, command_path)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET command_path = EXCLUDED.command_path, used_at = now()
            """,
            guild_id or 0,
            user_id,
            percorso[:MAX_PERCORSO],
        )
        self._scritture += 1
        if self._scritture >= self.ogni_n_scritture:
            self._scritture = 0
            try:
                await self.pulisci(self.giorni, self.tetto)
            except Exception:
                logger.warning("Pulizia di command_usage fallita.", exc_info=True)

    async def ultimo(self, guild_id: int | None, user_id: int) -> str | None:
        return await self._pool.fetchval(
            "SELECT command_path FROM command_usage WHERE guild_id = $1 AND user_id = $2",
            guild_id or 0,
            user_id,
        )

    async def pulisci(self, giorni: int = GIORNI_CONSERVAZIONE, tetto: int = TETTO_RIGHE) -> int:
        """Toglie le righe più vecchie di `giorni`, poi le più vecchie oltre `tetto`. Restituisce quante."""
        vecchie = await self._pool.execute(
            "DELETE FROM command_usage WHERE used_at < now() - make_interval(days => $1)", giorni
        )
        oltre = await self._pool.execute(
            """
            DELETE FROM command_usage WHERE (guild_id, user_id) IN (
                SELECT guild_id, user_id FROM command_usage
                ORDER BY used_at DESC OFFSET $1
            )
            """,
            tetto,
        )
        return _conta(vecchie) + _conta(oltre)


def _conta(esito: str) -> int:
    try:
        return int(esito.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


def _get_pool():
    from core.database import db

    return db.pool


command_usage_repo = CommandUsageRepository(pool_provider=_get_pool)
