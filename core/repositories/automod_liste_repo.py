"""
core/repositories/automod_liste_repo.py
=======================================
Righe della tabella `automod_liste` (migrazione 0500): liste con nome di parole o domini di ogni server.
Funzioni coperte: SPEC §6 (AMD-016), D63
"""

from __future__ import annotations


class AutomodListeRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    async def elenca(self, guild_id: int) -> list[tuple[str, str, tuple[str, ...]]]:
        righe = await self._pool.fetch("SELECT nome, tipo, voci FROM automod_liste WHERE guild_id = $1 ORDER BY nome", guild_id)
        return [(r["nome"], r["tipo"], tuple(r["voci"])) for r in righe]

    async def salva(self, guild_id: int, nome: str, tipo: str, voci: tuple[str, ...]) -> None:
        await self._pool.execute(
            "INSERT INTO automod_liste (guild_id, nome, tipo, voci) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (guild_id, nome) DO UPDATE SET tipo = EXCLUDED.tipo, voci = EXCLUDED.voci",
            guild_id, nome, tipo, list(voci))

    async def elimina(self, guild_id: int, nome: str) -> bool:
        esito = await self._pool.execute("DELETE FROM automod_liste WHERE guild_id = $1 AND nome = $2", guild_id, nome)
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db
    return db.pool


automod_liste_repo = AutomodListeRepository(pool_provider=_get_pool)
