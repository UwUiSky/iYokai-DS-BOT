"""
core/repositories/automod_decisioni_repo.py
===========================================
Decisioni chieste allo staff dalle regole AutoMod (migrazione 0503): le sanzioni restano qui finché un
moderatore preme «Applica» o «Ignora». La decisione si prende una volta sola, anche se due premono insieme.
Funzioni coperte: SPEC §6 (AMD-047), D63
"""

from __future__ import annotations

import json


class AutomodDecisioniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    async def crea(self, guild_id: int, user_id: int, regola_chiave: str, regola_nome: str, canale_id: int | None,
                   estratto: str | None, azioni: list[dict]) -> int:
        return await self._pool.fetchval(
            "INSERT INTO automod_decisioni (guild_id, user_id, regola_chiave, regola_nome, canale_id, estratto, azioni) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb) RETURNING id",
            guild_id, user_id, regola_chiave, regola_nome[:100], canale_id, (estratto or "")[:500] or None, json.dumps(azioni))

    async def imposta_messaggio(self, decisione_id: int, messaggio_id: int) -> None:
        await self._pool.execute("UPDATE automod_decisioni SET messaggio_id = $2 WHERE id = $1", decisione_id, messaggio_id)

    async def ottieni(self, decisione_id: int) -> dict | None:
        riga = await self._pool.fetchrow("SELECT * FROM automod_decisioni WHERE id = $1", decisione_id)
        if riga is None:
            return None
        d = dict(riga)
        d["azioni"] = json.loads(d["azioni"]) if isinstance(d["azioni"], str) else d["azioni"]
        return d

    async def decidi(self, decisione_id: int, guild_id: int, stato: str, staff_id: int) -> dict | None:
        """Chiude la decisione solo se è ancora in attesa e del server giusto. None se un altro ha già deciso."""
        riga = await self._pool.fetchrow(
            "UPDATE automod_decisioni SET stato = $3, decisa_da = $4, decisa_il = now() "
            "WHERE id = $1 AND guild_id = $2 AND stato = 'attesa' RETURNING *", decisione_id, guild_id, stato, staff_id)
        if riga is None:
            return None
        d = dict(riga)
        d["azioni"] = json.loads(d["azioni"]) if isinstance(d["azioni"], str) else d["azioni"]
        return d


def _get_pool():
    from core.database import db
    return db.pool


automod_decisioni_repo = AutomodDecisioniRepository(pool_provider=_get_pool)
