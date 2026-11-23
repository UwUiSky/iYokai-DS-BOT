"""
core/repositories/ruoli_collegati_verifica_repo.py
==================================================
Collegamento della verifica per i ruoli collegati di Discord (tabella `ruoli_collegati_verifica`, migrazione 0754).
I token arrivano già cifrati: qui non si cifra né si decifra niente.
Funzioni coperte: SPEC §24.11 (VER-027, issue #118)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class CollegamentoVerifica:
    user_id: int
    verificato: bool
    avatar_presente: bool
    collegato_il: datetime | None = None
    token: str = field(default="", repr=False)
    refresh: str | None = field(default=None, repr=False)
    scade_il: datetime | None = None


class RuoliCollegatiVerificaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def ha_superato_la_verifica(self, user_id: int) -> bool:
        """Ha già superato la verifica in almeno un server dove c'è il bot."""
        return bool(await self._pool.fetchval("SELECT EXISTS (SELECT 1 FROM verify_attempts WHERE user_id = $1 AND success)", user_id))

    async def salva(
        self, user_id: int, token: str, refresh: str | None, scade_il: datetime | None, verificato: bool, avatar: bool
    ) -> None:
        await self._pool.execute(
            "INSERT INTO ruoli_collegati_verifica (user_id, discord_token, discord_refresh, discord_scade_il, verificato, avatar_presente) "
            "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (user_id) DO UPDATE SET discord_token = EXCLUDED.discord_token, "
            "discord_refresh = EXCLUDED.discord_refresh, discord_scade_il = EXCLUDED.discord_scade_il, "
            "verificato = EXCLUDED.verificato, avatar_presente = EXCLUDED.avatar_presente, collegato_il = now(), aggiornato_il = now()",
            user_id, token, refresh, scade_il, verificato, avatar,
        )

    async def leggi(self, user_id: int) -> CollegamentoVerifica | None:
        riga = await self._pool.fetchrow(
            "SELECT user_id, discord_token AS token, discord_refresh AS refresh, discord_scade_il AS scade_il, verificato, "
            "avatar_presente, collegato_il FROM ruoli_collegati_verifica WHERE user_id = $1",
            user_id,
        )
        return CollegamentoVerifica(**dict(riga)) if riga else None

    async def aggiorna_valori(self, user_id: int, verificato: bool, avatar: bool) -> None:
        await self._pool.execute(
            "UPDATE ruoli_collegati_verifica SET verificato = $2, avatar_presente = $3, aggiornato_il = now() WHERE user_id = $1",
            user_id, verificato, avatar,
        )

    async def aggiorna_token(self, user_id: int, token: str, refresh: str | None, scade_il: datetime | None) -> None:
        await self._pool.execute(
            "UPDATE ruoli_collegati_verifica SET discord_token = $2, discord_refresh = $3, discord_scade_il = $4, aggiornato_il = now() "
            "WHERE user_id = $1",
            user_id, token, refresh, scade_il,
        )

    async def elimina(self, user_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM ruoli_collegati_verifica WHERE user_id = $1", user_id)
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


ruoli_collegati_verifica_repo = RuoliCollegatiVerificaRepository(pool_provider=_get_pool)
