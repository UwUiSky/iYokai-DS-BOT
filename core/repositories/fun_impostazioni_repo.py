"""
core/repositories/fun_impostazioni_repo.py
==========================================
Impostazioni del Divertimento di ogni server (`fun_impostazioni`): pacchetti delle carte e pacchetto «adulti»
(spento di base). Una sola istruzione per scrittura. Tabella: core/migrations/0572_fun_impostazioni.sql.
Funzioni coperte: SPEC §16 (FUN-007; #131)
"""

from __future__ import annotations

import asyncpg


class FunImpostazioniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def carte(self, guild_id: int) -> tuple[str, bool]:
        """(pacchetti separati da virgola, adulti acceso). Di base: base,nerd,gamer e adulti spento."""
        r = await self._pool.fetchrow("SELECT carte_pacchetti, carte_adulti FROM fun_impostazioni WHERE guild_id = $1", guild_id)
        return (r["carte_pacchetti"], r["carte_adulti"]) if r else ("base,nerd,gamer", False)

    async def imposta_carte(self, guild_id: int, pacchetti: str | None, adulti: bool | None) -> tuple[str, bool]:
        r = await self._pool.fetchrow(
            "INSERT INTO fun_impostazioni (guild_id, carte_pacchetti, carte_adulti) "
            "VALUES ($1, COALESCE($2, 'base,nerd,gamer'), COALESCE($3, FALSE)) "
            "ON CONFLICT (guild_id) DO UPDATE SET carte_pacchetti = COALESCE($2, fun_impostazioni.carte_pacchetti), "
            "carte_adulti = COALESCE($3, fun_impostazioni.carte_adulti) RETURNING carte_pacchetti, carte_adulti",
            guild_id, pacchetti, adulti,
        )
        return r["carte_pacchetti"], r["carte_adulti"]


def _get_pool():
    from core.database import db

    return db.pool


fun_impostazioni_repo = FunImpostazioniRepository(pool_provider=_get_pool)
