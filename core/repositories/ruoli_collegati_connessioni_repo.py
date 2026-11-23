"""
core/repositories/ruoli_collegati_connessioni_repo.py
=====================================================
Se il profilo Discord di una persona ha Twitch o Kick collegati (tabella `ruoli_collegati_connessioni`, migrazione 0960).
Due sì/no e la data: niente nomi, niente ID, niente token. Si scrive solo dopo il consenso OAuth `connections`.
Funzioni coperte: SPEC §24.9 (ALR-049, D127)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class Connessioni:
    user_id: int
    ha_twitch: bool
    ha_kick: bool
    controllato_il: datetime


class RuoliCollegatiConnessioniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def salva(self, user_id: int, ha_twitch: bool, ha_kick: bool) -> None:
        await self._pool.execute(
            "INSERT INTO ruoli_collegati_connessioni (user_id, ha_twitch, ha_kick) VALUES ($1, $2, $3) "
            "ON CONFLICT (user_id) DO UPDATE SET ha_twitch = EXCLUDED.ha_twitch, ha_kick = EXCLUDED.ha_kick, controllato_il = now()",
            user_id, ha_twitch, ha_kick,
        )

    async def leggi(self, user_id: int) -> Connessioni | None:
        riga = await self._pool.fetchrow(
            "SELECT user_id, ha_twitch, ha_kick, controllato_il FROM ruoli_collegati_connessioni WHERE user_id = $1", user_id
        )
        return Connessioni(**dict(riga)) if riga else None

    async def elimina(self, user_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM ruoli_collegati_connessioni WHERE user_id = $1", user_id)
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


ruoli_collegati_connessioni_repo = RuoliCollegatiConnessioniRepository(pool_provider=_get_pool)
