"""
core/repositories/potenziamenti_repo.py
=======================================
Potenziamenti personali (ECO-081) e scrigni a sorpresa (ECO-077). Il costo si toglie con una UPDATE
condizionata e il livello sale solo se era quello atteso (nella stessa transazione): due acquisti insieme
non saltano due livelli con un solo pagamento. Le monete spese vanno alla cassa del server.
Funzioni coperte: ECO-077, ECO-081
"""

from __future__ import annotations

import asyncpg

from core.leveling_logic import LIVELLI_POTENZIAMENTO, TIPI_POTENZIAMENTO, costo_potenziamento
from core.repositories.guild_chest_repo import REASON_POTENZIAMENTO, deposit_in
from core.repositories.leveling_repo import add_coins_in, spend_coins_in

PAUSA_SCRIGNO = 30


class PotenziamentiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def livelli(self, guild_id: int, user_id: int) -> dict[str, int]:
        righe = await self._pool.fetch(
            "SELECT tipo, livello FROM economia_potenziamenti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        base = {t: 0 for t in TIPI_POTENZIAMENTO}
        base.update({r["tipo"]: r["livello"] for r in righe})
        return base

    async def compra(self, guild_id: int, user_id: int, tipo: str) -> tuple[str, int]:
        """
        Sale di un livello. Restituisce ("ok", nuovo livello), ("massimo", livello) o ("poche", costo).
        """
        if tipo not in TIPI_POTENZIAMENTO:
            raise ValueError(f"Tipo sconosciuto: {tipo}")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO economia_potenziamenti (guild_id, user_id, tipo) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    guild_id, user_id, tipo,
                )
                attuale = await conn.fetchval(
                    "SELECT livello FROM economia_potenziamenti WHERE guild_id = $1 AND user_id = $2 AND tipo = $3 FOR UPDATE",
                    guild_id, user_id, tipo,
                )
                costo = costo_potenziamento(attuale)
                if costo is None:
                    return "massimo", attuale
                if not await spend_coins_in(conn, guild_id, user_id, costo):
                    return "poche", costo
                await conn.execute(
                    "UPDATE economia_potenziamenti SET livello = livello + 1 WHERE guild_id = $1 AND user_id = $2 AND tipo = $3 AND livello = $4",
                    guild_id, user_id, tipo, attuale,
                )
                await deposit_in(conn, guild_id, costo, REASON_POTENZIAMENTO)
                return "ok", attuale + 1

    async def scrigno(
        self, guild_id: int, user_id: int, prezzo: int, premio: int, chiave: str = "scrigno", pausa_s: int = PAUSA_SCRIGNO
    ) -> int | None:
        """
        ECO-077: paga `prezzo` e riceve `premio` (anche 0) in una transazione, con una pausa tra due scrigni.
        Il prezzo va alla cassa, il premio è creato dal gioco come ogni vincita. None se pausa o saldo non bastano.
        """
        if prezzo <= 0 or premio < 0:
            raise ValueError("Prezzo o premio non validi.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                preso = await conn.fetchval(
                    "INSERT INTO economia_pause (guild_id, user_id, chiave, ultima_at) VALUES ($1, $2, $3, now()) "
                    "ON CONFLICT (guild_id, user_id, chiave) DO UPDATE SET ultima_at = now() "
                    "WHERE economia_pause.ultima_at <= now() - make_interval(secs => $4) RETURNING 1",
                    guild_id, user_id, chiave, float(pausa_s),
                )
                if preso is None or not await spend_coins_in(conn, guild_id, user_id, prezzo):
                    return None
                await deposit_in(conn, guild_id, prezzo, REASON_POTENZIAMENTO)
                if premio > 0:
                    return await add_coins_in(conn, guild_id, user_id, premio, classifica=False)
                return await conn.fetchval(
                    "SELECT coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                )


def _get_pool():
    from core.database import db

    return db.pool


potenziamenti_repo = PotenziamentiRepository(pool_provider=_get_pool)
