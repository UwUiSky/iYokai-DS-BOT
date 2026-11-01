"""
core/repositories/profile_repo.py
=================================
Profilo personale per server: presentazione, badge e sfondo scelti, oggetti
comprati con le coin. L'acquisto è una transazione sola: oggetto registrato
e coin tolte insieme, oppure niente.
Funzioni coperte: SPEC §23.16 (NF-40)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import asyncpg

from core.profile_logic import PER_ID, TIPI, TIPO_BADGE


class _SaldoInsufficiente(Exception):
    """Interna: serve a far annullare la transazione dell'acquisto."""


class EsitoAcquisto(enum.Enum):
    COMPRATO = "comprato"
    GIA_POSSEDUTO = "gia_posseduto"
    SALDO_INSUFFICIENTE = "saldo_insufficiente"
    SCONOSCIUTO = "sconosciuto"


@dataclass(frozen=True)
class Profilo:
    bio: str | None = None
    badge_id: str | None = None
    background_id: str | None = None
    posseduti: frozenset[str] = field(default_factory=frozenset)


async def regala_oggetti_in(conn, guild_id: int, user_id: int, item_ids: list[str]) -> list[str]:
    """
    Dà gli oggetti (premi estetici) dentro una transazione già aperta. Restituisce quelli nuovi: chi li
    aveva già non li riceve due volte. Gli id fuori dal catalogo si ignorano.
    """
    validi = [i for i in item_ids if i in PER_ID]
    if not validi:
        return []
    righe = await conn.fetch(
        "INSERT INTO profile_items (guild_id, user_id, item_id) SELECT $1, $2, i FROM unnest($3::text[]) AS i "
        "ON CONFLICT DO NOTHING RETURNING item_id",
        guild_id, user_id, validi,
    )
    return [r["item_id"] for r in righe]


class ProfileRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_profile(self, guild_id: int, user_id: int) -> Profilo:
        riga = await self._pool.fetchrow(
            "SELECT bio, badge_id, background_id FROM profile_settings "
            "WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )
        oggetti = await self._pool.fetch(
            "SELECT item_id FROM profile_items WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )
        posseduti = frozenset(r["item_id"] for r in oggetti if r["item_id"] in PER_ID)
        if riga is None:
            return Profilo(posseduti=posseduti)
        return Profilo(riga["bio"], riga["badge_id"], riga["background_id"], posseduti)

    async def set_bio(self, guild_id: int, user_id: int, bio: str | None) -> None:
        await self._pool.execute(
            """
            INSERT INTO profile_settings (guild_id, user_id, bio) VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET bio = EXCLUDED.bio
            """,
            guild_id,
            user_id,
            bio or None,
        )

    async def buy(self, guild_id: int, user_id: int, item_id: str) -> EsitoAcquisto:
        """
        Compra un oggetto del catalogo. Registrazione e addebito stanno nella
        stessa transazione, e il prezzo viene dal catalogo, mai dal chiamante:
        due acquisti insieme dello stesso oggetto ne addebitano uno solo.
        """
        from core.repositories.leveling_repo import spend_coins_in

        oggetto = PER_ID.get(item_id)
        if oggetto is None or oggetto.premio:  # i premi non si comprano
            return EsitoAcquisto.SCONOSCIUTO
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    nuovo = await conn.fetchval(
                        "INSERT INTO profile_items (guild_id, user_id, item_id) VALUES ($1, $2, $3) "
                        "ON CONFLICT DO NOTHING RETURNING 1",
                        guild_id,
                        user_id,
                        item_id,
                    )
                    if nuovo is None:
                        return EsitoAcquisto.GIA_POSSEDUTO
                    if not await spend_coins_in(conn, guild_id, user_id, oggetto.prezzo):
                        raise _SaldoInsufficiente()  # annulla anche la riga appena scritta
        except _SaldoInsufficiente:
            return EsitoAcquisto.SALDO_INSUFFICIENTE
        return EsitoAcquisto.COMPRATO

    async def equip(self, guild_id: int, user_id: int, tipo: str, item_id: str | None) -> bool:
        """
        Mette badge o sfondo (o li toglie, con `item_id` None). False se
        l'oggetto non è del tipo giusto o non è posseduto.
        """
        if tipo not in TIPI:
            raise ValueError(f"Tipo sconosciuto: {tipo}")
        colonna = "badge_id" if tipo == TIPO_BADGE else "background_id"
        if item_id is None:
            await self._pool.execute(
                f"""
                INSERT INTO profile_settings (guild_id, user_id, {colonna}) VALUES ($1, $2, NULL)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET {colonna} = NULL
                """,
                guild_id,
                user_id,
            )
            return True
        oggetto = PER_ID.get(item_id)
        if oggetto is None or oggetto.tipo != tipo:
            return False
        risultato = await self._pool.fetchval(
            f"""
            WITH posseduto AS (
                SELECT 1 FROM profile_items WHERE guild_id = $1 AND user_id = $2 AND item_id = $3
            )
            INSERT INTO profile_settings (guild_id, user_id, {colonna})
            SELECT $1, $2, $3 FROM posseduto
            ON CONFLICT (guild_id, user_id) DO UPDATE SET {colonna} = EXCLUDED.{colonna}
            RETURNING 1
            """,
            guild_id,
            user_id,
            item_id,
        )
        return risultato is not None


def _get_pool():
    from core.database import db

    return db.pool


profile_repo = ProfileRepository(pool_provider=_get_pool)
