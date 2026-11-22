"""
core/repositories/animali_avanzati_repo.py
==========================================
Animali avanzati: sitter, lotte, incontri con cuccioli, abbandono e adozione. Un animale senza padrone ha
user_id = 0 (coda di adozione, massimo 20 per server). Ogni passaggio è una transazione: le righe degli
animali si bloccano in ordine di ID, l'adozione è una UPDATE condizionata (`user_id = 0`), quindi due persone
non adottano lo stesso animale.
Funzioni coperte: ECO-125, ECO-126, ECO-127, ECO-128, ECO-129
"""

from __future__ import annotations

from datetime import date

import asyncpg

from core.animali_avanzati_logic import (
    CODA_ADOZIONE_MAX, NOME_CUCCIOLO, PAUSA_LOTTA, XP_INCONTRO, XP_SCONFITTA, XP_VITTORIA, costo_sitter,
)
from core.animali_logic import POSTI_BASE
from core.repositories.guild_chest_repo import deposit_in
from core.repositories.leveling_repo import spend_coins_in

REASON_SITTER = "animali_sitter"
SENZA_PADRONE = 0


class AnimaliAvanzatiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def sitter(self, guild_id: int, user_id: int, animale_id: int, giorni: int) -> str:
        """«ok», «non_tuo», «attivo» (c'è già un sitter) o «poche». Il costo va alla cassa; i bisogni restano pieni per i giorni pagati."""
        costo = costo_sitter(giorni)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                riga = await conn.fetchrow(
                    "SELECT sitter_fino > now() AS attivo FROM economia_animali WHERE id = $1 AND guild_id = $2 AND user_id = $3 FOR UPDATE",
                    animale_id, guild_id, user_id,
                )
                if riga is None:
                    return "non_tuo"
                if riga["attivo"]:
                    return "attivo"
                if not await spend_coins_in(conn, guild_id, user_id, costo, REASON_SITTER):
                    return "poche"
                await deposit_in(conn, guild_id, costo, REASON_SITTER)
                await conn.execute(
                    "UPDATE economia_animali SET sitter_fino = now() + make_interval(days => $2), fame_at = now() + make_interval(days => $2), "
                    "igiene_at = now() + make_interval(days => $2), gioco_at = now() + make_interval(days => $2) WHERE id = $1",
                    animale_id, giorni,
                )
                return "ok"

    async def lotta(self, guild_id: int, mio_id: int, mio_user: int, suo_id: int, suo_user: int, vince_mio: bool) -> str:
        """Lotta senza puntata: esperienza a tutti e due (più al vincitore), pausa di un'ora per animale. «ok», «pausa», «non_tuo»."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    "SELECT id, user_id, lotta_at > now() - make_interval(secs => $3) AS in_pausa FROM economia_animali "
                    "WHERE guild_id = $1 AND id = ANY($2::bigint[]) ORDER BY id FOR UPDATE", guild_id, [mio_id, suo_id], float(PAUSA_LOTTA),
                )
                di = {r["id"]: r for r in righe}
                if len(di) != 2 or di[mio_id]["user_id"] != mio_user or di[suo_id]["user_id"] != suo_user:
                    return "non_tuo"
                if di[mio_id]["in_pausa"] or di[suo_id]["in_pausa"]:
                    return "pausa"
                for aid, vinto in ((mio_id, vince_mio), (suo_id, not vince_mio)):
                    await conn.execute(
                        "UPDATE economia_animali SET lotta_at = now(), xp = xp + $2 WHERE id = $1", aid, XP_VITTORIA if vinto else XP_SCONFITTA
                    )
                return "ok"

    async def incontro(
        self, guild_id: int, giorno: date, mio_id: int, mio_user: int, suo_id: int, suo_user: int, nasce: bool, specie: str
    ) -> tuple[str, bool]:
        """
        Gli animali giocano insieme (gioco al massimo, un po' di esperienza). Una volta al giorno per coppia.
        Se `nasce`, un cucciolo senza padrone entra nella coda di adozione (se non è piena). («ok»/«gia»/«non_tuo», nato).
        """
        a, b = sorted((mio_id, suo_id))
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    "SELECT id, user_id FROM economia_animali WHERE guild_id = $1 AND id = ANY($2::bigint[]) ORDER BY id FOR UPDATE", guild_id, [a, b]
                )
                di = {r["id"]: r["user_id"] for r in righe}
                if len(di) != 2 or di[mio_id] != mio_user or di[suo_id] != suo_user:
                    return "non_tuo", False
                if await conn.fetchval(
                    "INSERT INTO economia_animali_incontri (guild_id, giorno, a_id, b_id) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING RETURNING 1",
                    guild_id, giorno, a, b,
                ) is None:
                    return "gia", False
                await conn.execute(
                    "UPDATE economia_animali SET gioco_at = GREATEST(gioco_at, now()), xp = xp + $2 WHERE id = ANY($1::bigint[])", [a, b], XP_INCONTRO
                )
                nato = False
                if nasce:
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"adozioni:{guild_id}")
                    if await conn.fetchval("SELECT count(*) FROM economia_animali WHERE guild_id = $1 AND user_id = $2", guild_id, SENZA_PADRONE) < CODA_ADOZIONE_MAX:
                        await conn.execute(
                            "INSERT INTO economia_animali (guild_id, user_id, specie, nome) VALUES ($1, $2, $3, $4)", guild_id, SENZA_PADRONE, specie, NOME_CUCCIOLO
                        )
                        nato = True
                return "ok", nato

    async def abbandona(self, guild_id: int, user_id: int, animale_id: int) -> str:
        """L'animale va nella coda di adozione. «ok», «non_tuo» o «piena»."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"adozioni:{guild_id}")
                if await conn.fetchval("SELECT count(*) FROM economia_animali WHERE guild_id = $1 AND user_id = $2", guild_id, SENZA_PADRONE) >= CODA_ADOZIONE_MAX:
                    return "piena"
                fatto = await conn.fetchval(
                    "UPDATE economia_animali SET user_id = $4, ex_proprietario = $3 WHERE id = $1 AND guild_id = $2 AND user_id = $3 RETURNING 1",
                    animale_id, guild_id, user_id, SENZA_PADRONE,
                )
                return "ok" if fatto else "non_tuo"

    async def da_adottare(self, guild_id: int, limite: int = 10) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT id, specie, nome, xp FROM economia_animali WHERE guild_id = $1 AND user_id = $2 ORDER BY id LIMIT $3",
            guild_id, SENZA_PADRONE, min(max(1, limite), 25),
        )

    async def adotta(self, guild_id: int, user_id: int, animale_id: int) -> str:
        """«ok», «non_c_e» (già preso), «pieno» (nessun posto libero) o «tuo_ex» (non si riprende un animale lasciato da sé)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"animali:{guild_id}:{user_id}")
                extra = await conn.fetchval("SELECT extra FROM economia_animali_posti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                avuti = await conn.fetchval("SELECT count(*) FROM economia_animali WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                if avuti >= POSTI_BASE + int(extra or 0):
                    return "pieno"
                riga = await conn.fetchrow(
                    "UPDATE economia_animali SET user_id = $3, ex_proprietario = NULL, fame_at = GREATEST(fame_at, now() - interval '12 hours') "
                    "WHERE id = $1 AND guild_id = $2 AND user_id = $4 AND ex_proprietario IS DISTINCT FROM $3 RETURNING 1",
                    animale_id, guild_id, user_id, SENZA_PADRONE,
                )
                if riga:
                    return "ok"
                esiste = await conn.fetchval("SELECT ex_proprietario FROM economia_animali WHERE id = $1 AND guild_id = $2 AND user_id = $3",
                                             animale_id, guild_id, SENZA_PADRONE)
                return "tuo_ex" if esiste == user_id else "non_c_e"


def _get_pool():
    from core.database import db

    return db.pool


animali_avanzati_repo = AnimaliAvanzatiRepository(pool_provider=_get_pool)
