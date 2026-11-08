"""
core/repositories/automod_pulizie_repo.py
=========================================
Righe della tabella `automod_pulizie` (pulizia di un canale a intervalli). Solo lettura e scrittura; le regole stanno
in core/automod_pulizia_logic.py. La tabella nasce nella migrazione 0509.
Funzioni coperte: SPEC §6 (AMD-073, 074)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Pulizia:
    guild_id: int
    canale_id: int
    ogni_secondi: int
    tipo: str
    fissati: bool
    attiva: bool
    ultimo_giro: datetime | None = None


def _pulizia(r) -> Pulizia:
    return Pulizia(r["guild_id"], r["canale_id"], r["ogni_secondi"], r["tipo"], r["fissati"], r["attiva"], r["ultimo_giro"])


class AutomodPulizieRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    async def elenca(self, guild_id: int) -> list[Pulizia]:
        return [_pulizia(r) for r in await self._pool.fetch(
            "SELECT * FROM automod_pulizie WHERE guild_id = $1 ORDER BY canale_id", guild_id)]

    async def conta(self, guild_id: int) -> int:
        return await self._pool.fetchval("SELECT count(*) FROM automod_pulizie WHERE guild_id = $1", guild_id)

    async def leggi(self, guild_id: int, canale_id: int) -> Pulizia | None:
        r = await self._pool.fetchrow("SELECT * FROM automod_pulizie WHERE guild_id = $1 AND canale_id = $2", guild_id, canale_id)
        return None if r is None else _pulizia(r)

    async def salva(self, p: Pulizia, autore_id: int | None) -> None:
        """Crea o cambia la riga. Quando si cambia, il prossimo giro riparte da adesso (mai una pulizia a sorpresa)."""
        await self._pool.execute(
            """INSERT INTO automod_pulizie (guild_id, canale_id, ogni_secondi, tipo, fissati, attiva, creata_da)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               ON CONFLICT (guild_id, canale_id) DO UPDATE SET ogni_secondi = EXCLUDED.ogni_secondi, tipo = EXCLUDED.tipo,
                   fissati = EXCLUDED.fissati, attiva = EXCLUDED.attiva, ultimo_giro = now()""",
            p.guild_id, p.canale_id, p.ogni_secondi, p.tipo, p.fissati, p.attiva, autore_id)

    async def elimina(self, guild_id: int, canale_id: int) -> bool:
        return (await self._pool.execute(
            "DELETE FROM automod_pulizie WHERE guild_id = $1 AND canale_id = $2", guild_id, canale_id)).endswith(" 1")

    async def spegni(self, guild_id: int, canale_id: int) -> None:
        await self._pool.execute(
            "UPDATE automod_pulizie SET attiva = FALSE WHERE guild_id = $1 AND canale_id = $2", guild_id, canale_id)

    async def riserva_dovute(self, massimo: int) -> list[Pulizia]:
        """Le pulizie da fare adesso (al massimo `massimo`). Il giro si segna PRIMA di cancellare: se il bot si ferma
        a metà, la pulizia non riparte subito e due giri non si sovrappongono."""
        righe = await self._pool.fetch(
            """UPDATE automod_pulizie SET ultimo_giro = now()
               WHERE (guild_id, canale_id) IN (
                   SELECT guild_id, canale_id FROM automod_pulizie
                   WHERE attiva AND ultimo_giro + ogni_secondi * interval '1 second' <= now()
                   ORDER BY ultimo_giro LIMIT $1 FOR UPDATE SKIP LOCKED)
               RETURNING *""", massimo)
        return [_pulizia(r) for r in righe]


def _get_pool():
    from core.database import db
    return db.pool


automod_pulizie_repo = AutomodPulizieRepository(pool_provider=_get_pool)
