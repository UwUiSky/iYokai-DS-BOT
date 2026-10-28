"""
core/repositories/ai_ticket_repo.py
===================================
Prima risposta automatica dell'AI nei ticket: pannelli che la usano e ticket che l'hanno già avuta (una sola).
Funzioni coperte: SPEC §25.66 (AI-R-072)
"""

from __future__ import annotations

import asyncpg


class AiTicketRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def prima_risposta_attiva(self, guild_id: int, panel_id: int) -> bool:
        return bool(await self._pool.fetchval(
            "SELECT prima_risposta FROM ai_ticket_pannelli WHERE guild_id = $1 AND panel_id = $2", guild_id, panel_id
        ))

    async def imposta_prima_risposta(self, guild_id: int, panel_id: int, attiva: bool) -> None:
        await self._pool.execute(
            "INSERT INTO ai_ticket_pannelli (guild_id, panel_id, prima_risposta) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id, panel_id) DO UPDATE SET prima_risposta = EXCLUDED.prima_risposta",
            guild_id, panel_id, attiva,
        )

    async def prenota_risposta(self, channel_id: int, guild_id: int) -> bool:
        """True solo la prima volta per canale: un solo messaggio automatico per ticket."""
        esito = await self._pool.execute(
            "INSERT INTO ai_ticket_risposte (channel_id, guild_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", channel_id, guild_id
        )
        return esito.endswith(" 1")

    async def rilascia_risposta(self, channel_id: int) -> None:
        """Se l'AI non ha potuto rispondere, il posto si libera per un altro tentativo."""
        await self._pool.execute("DELETE FROM ai_ticket_risposte WHERE channel_id = $1", channel_id)

    # ------------------------------------------------------------ file delle risposte standard
    async def salva_allegati(self, guild_id: int, reply_id: int, file: list[tuple[str, bytes]]) -> int:
        """Conserva i file (già scelti entro i tetti di dimensione); restituisce quanti."""
        for nome, contenuto in file:
            await self._pool.execute(
                "INSERT INTO ai_standard_allegati (guild_id, reply_id, filename, contenuto) VALUES ($1, $2, $3, $4)",
                guild_id, reply_id, nome[:200], contenuto,
            )
        return len(file)

    async def allegati_di(self, reply_id: int) -> list[tuple[str, bytes]]:
        righe = await self._pool.fetch("SELECT filename, contenuto FROM ai_standard_allegati WHERE reply_id = $1 ORDER BY id", reply_id)
        return [(r["filename"], bytes(r["contenuto"])) for r in righe]


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


ai_ticket_repo = AiTicketRepository(pool_provider=_get_pool)
