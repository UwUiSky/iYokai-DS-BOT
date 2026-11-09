"""
core/repositories/inviti_extra_repo.py
======================================
Bonus dello staff e esclusi dalla classifica degli inviti (D69 B11). Tabelle: core/migrations/0549.
Funzioni coperte: catalogo UTL-169, 170, 171, 172, 173
"""

from __future__ import annotations

import asyncpg

from core.invite_links_logic import MAX_BONUS, MAX_ESCLUSI
from core.inviti_codici_logic import MAX_ETICHETTE_SERVER


class TroppiEsclusi(Exception):
    """Il server ha già il massimo di esclusi."""


class TroppeEtichette(Exception):
    """Il server ha già il massimo di etichette."""


class InvitiExtraRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def aggiungi_bonus(self, guild_id: int, user_id: int, quanti: int, dato_da: int | None) -> int:
        """Somma `quanti` (anche negativo) al bonus del membro. Il totale resta tra -100000 e 100000. Ritorna il totale."""
        if not -MAX_BONUS <= quanti <= MAX_BONUS:
            raise ValueError("bonus fuori misura")
        return await self._pool.fetchval(
            """
            INSERT INTO inviti_bonus (guild_id, user_id, quanti, dato_da) VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET quanti = GREATEST(-100000, LEAST(100000, inviti_bonus.quanti + EXCLUDED.quanti)),
                    dato_da = EXCLUDED.dato_da
            RETURNING quanti
            """,
            guild_id, user_id, quanti, dato_da,
        )

    async def aggiungi_escluso(self, guild_id: int, tipo: str, id_: int) -> bool:
        """True se è nuovo. TroppiEsclusi se il server è al tetto."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext('inviti_esclusi'), $1)", guild_id % 2**31)
                if await conn.fetchval("SELECT count(*) FROM inviti_esclusi WHERE guild_id = $1", guild_id) >= MAX_ESCLUSI:
                    if not await conn.fetchval(
                        "SELECT 1 FROM inviti_esclusi WHERE guild_id = $1 AND tipo = $2 AND id = $3", guild_id, tipo, id_
                    ):
                        raise TroppiEsclusi()
                esito = await conn.execute(
                    "INSERT INTO inviti_esclusi (guild_id, tipo, id) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    guild_id, tipo, id_,
                )
        return esito.endswith(" 1")

    async def togli_escluso(self, guild_id: int, tipo: str, id_: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM inviti_esclusi WHERE guild_id = $1 AND tipo = $2 AND id = $3", guild_id, tipo, id_
        )
        return esito.endswith(" 1")

    async def esclusi(self, guild_id: int) -> tuple[set[int], set[int]]:
        """(utenti esclusi, ruoli esclusi)."""
        righe = await self._pool.fetch("SELECT tipo, id FROM inviti_esclusi WHERE guild_id = $1", guild_id)
        return ({r["id"] for r in righe if r["tipo"] == "utente"}, {r["id"] for r in righe if r["tipo"] == "ruolo"})

    # ---------------------------------------------------------------- etichette dei codici (B12)
    async def imposta_etichetta(self, guild_id: int, codice: str, etichetta: str, ruolo_id: int | None) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext('inviti_etichette'), $1)", guild_id % 2**31)
                esiste = await conn.fetchval(
                    "SELECT 1 FROM inviti_etichette WHERE guild_id = $1 AND codice = $2", guild_id, codice
                )
                if not esiste and await conn.fetchval(
                    "SELECT count(*) FROM inviti_etichette WHERE guild_id = $1", guild_id
                ) >= MAX_ETICHETTE_SERVER:
                    raise TroppeEtichette()
                await conn.execute(
                    "INSERT INTO inviti_etichette (guild_id, codice, etichetta, ruolo_id) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (guild_id, codice) DO UPDATE SET etichetta = EXCLUDED.etichetta, ruolo_id = EXCLUDED.ruolo_id",
                    guild_id, codice, etichetta, ruolo_id,
                )

    async def etichette_di(self, guild_id: int, codici: list[str]) -> dict[str, tuple[str, int | None]]:
        """codice -> (etichetta, ruolo) per i codici dati."""
        if not codici:
            return {}
        righe = await self._pool.fetch(
            "SELECT codice, etichetta, ruolo_id FROM inviti_etichette WHERE guild_id = $1 AND codice = ANY($2::text[])",
            guild_id, codici,
        )
        return {r["codice"]: (r["etichetta"], r["ruolo_id"]) for r in righe}

    async def togli_etichetta(self, guild_id: int, codice: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM inviti_etichette WHERE guild_id = $1 AND codice = $2", guild_id, codice
        )
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db
    return db.pool


inviti_extra_repo = InvitiExtraRepository(pool_provider=_get_pool)
