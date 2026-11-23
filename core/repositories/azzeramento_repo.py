"""
core/repositories/azzeramento_repo.py
=====================================
Le richieste di azzerare i dati di un server (tabella `richieste_azzeramento`, migrazione 0831).
Funzioni coperte: SPEC §19 (NF-04), catalogo #128 (UTL-228)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class Richiesta:
    guild_id: int
    richiesto_da: int
    proprietario_id: int
    richiesta_il: datetime
    esegui_il: datetime
    stato: str
    azione_preavviso_id: int | None
    azione_esegui_id: int | None


def _da_riga(r) -> Richiesta:
    return Richiesta(**{k: r[k] for k in Richiesta.__dataclass_fields__})


class AzzeramentoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get(self, guild_id: int, conn=None) -> Richiesta | None:
        r = await (conn or self._pool).fetchrow("SELECT * FROM richieste_azzeramento WHERE guild_id = $1", guild_id)
        return _da_riga(r) if r else None

    async def crea(self, guild_id: int, richiesto_da: int, proprietario_id: int, esegui_il: datetime) -> Richiesta | None:
        """None se per il server c'è già una richiesta (attiva o sospesa)."""
        r = await self._pool.fetchrow(
            """
            INSERT INTO richieste_azzeramento (guild_id, richiesto_da, proprietario_id, esegui_il)
            VALUES ($1, $2, $3, $4) ON CONFLICT (guild_id) DO NOTHING RETURNING *
            """,
            guild_id, richiesto_da, proprietario_id, esegui_il,
        )
        return _da_riga(r) if r else None

    async def imposta_azioni(self, guild_id: int, preavviso_id: int | None, esegui_id: int | None) -> None:
        await self._pool.execute(
            "UPDATE richieste_azzeramento SET azione_preavviso_id = $2, azione_esegui_id = $3 WHERE guild_id = $1",
            guild_id, preavviso_id, esegui_id,
        )

    async def elimina(self, guild_id: int) -> Richiesta | None:
        """Toglie la richiesta (annullata o eseguita) e restituisce com'era."""
        r = await self._pool.fetchrow("DELETE FROM richieste_azzeramento WHERE guild_id = $1 RETURNING *", guild_id)
        return _da_riga(r) if r else None

    async def sospendi(self, guild_id: int, proprietario_attuale: int) -> Richiesta | None:
        """Sospende una richiesta attiva (il proprietario è cambiato). None se non era attiva."""
        r = await self._pool.fetchrow(
            """
            UPDATE richieste_azzeramento SET stato = 'sospesa', proprietario_id = $2
            WHERE guild_id = $1 AND stato = 'attiva' RETURNING *
            """,
            guild_id, proprietario_attuale,
        )
        return _da_riga(r) if r else None

    async def riprendi(self, guild_id: int, user_id: int, esegui_il: datetime) -> Richiesta | None:
        """Il nuovo proprietario conferma: la richiesta riparte con una scadenza nuova. None se non era sospesa."""
        r = await self._pool.fetchrow(
            """
            UPDATE richieste_azzeramento
            SET stato = 'attiva', richiesto_da = $2, proprietario_id = $2, esegui_il = $3
            WHERE guild_id = $1 AND stato = 'sospesa' RETURNING *
            """,
            guild_id, user_id, esegui_il,
        )
        return _da_riga(r) if r else None

    async def attive_scadute(self, adesso: datetime) -> list[int]:
        """I server con una richiesta attiva la cui data è passata (rete di sicurezza se lo scheduler non ha eseguito)."""
        righe = await self._pool.fetch(
            "SELECT guild_id FROM richieste_azzeramento WHERE stato = 'attiva' AND esegui_il <= $1", adesso
        )
        return [r["guild_id"] for r in righe]


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


azzeramento_repo = AzzeramentoRepository(pool_provider=_get_pool)
