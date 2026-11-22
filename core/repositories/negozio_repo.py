"""
core/repositories/negozio_repo.py
=================================
Negozio avanzato: oggetti a rotazione (ECO-075), offerte lampo con scadenza (ECO-076), ricette (ECO-078).
Il prezzo effettivo si calcola in `shop_repo.prezzo_di_oggi_in` (dentro la transazione d'acquisto); qui ci
sono le letture per la vetrina (stessa funzione di calcolo) e la creazione. La ricetta toglie gli
ingredienti con UPDATE condizionate e dà il risultato nella stessa transazione.
Funzioni coperte: ECO-075, ECO-076, ECO-078
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum

import asyncpg

from core.negozio_logic import MAX_INGREDIENTI, MAX_RICETTE, prezzo_con_sconto, scelti_rotazione
from core.repositories.inventario_repo import _PULISCI
from core.repositories.leveling_repo import spend_coins_in


class EsitoRicetta(str, Enum):
    FATTO = "fatto"
    NON_ESISTE = "non_esiste"
    MANCANO = "mancano"
    POCHE_MONETE = "poche_monete"


@dataclass(frozen=True)
class Offerta:
    id: int
    item_id: int
    sconto_pct: int
    scade_at: datetime
    usi_max: int | None
    usi: int


@dataclass(frozen=True)
class Ricetta:
    id: int
    nome: str
    risultato_item: int
    risultato_q: int
    costo: int
    ingredienti: tuple[tuple[int, int], ...]  # (item_id, quantità)


class NegozioRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ rotazione
    async def imposta_rotazione(self, guild_id: int, quanti: int) -> None:
        await self._pool.execute(
            "INSERT INTO economia_negozio_conf (guild_id, rotazione_quanti) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET rotazione_quanti = EXCLUDED.rotazione_quanti", guild_id, quanti,
        )

    async def imposta_a_rotazione(self, guild_id: int, item_id: int, si: bool) -> bool:
        r = await self._pool.execute("UPDATE shop_items SET a_rotazione = $3 WHERE id = $1 AND guild_id = $2", item_id, guild_id, si)
        return r.endswith(" 1")

    async def rotazione_quanti(self, guild_id: int) -> int:
        return await self._pool.fetchval("SELECT rotazione_quanti FROM economia_negozio_conf WHERE guild_id = $1", guild_id) or 0

    async def in_vetrina(self, guild_id: int, giorno: date | None = None) -> set[int] | None:
        """Gli ID a rotazione in vetrina oggi; None se la rotazione è spenta."""
        quanti = await self.rotazione_quanti(guild_id)
        if quanti <= 0:
            return None
        ids = [r["id"] for r in await self._pool.fetch("SELECT id FROM shop_items WHERE guild_id = $1 AND a_rotazione", guild_id)]
        return scelti_rotazione(ids, guild_id, giorno or datetime.now(timezone.utc).date(), quanti)

    # ------------------------------------------------------------ offerte lampo
    async def crea_offerta(self, guild_id: int, item_id: int, sconto_pct: int, minuti: int, usi_max: int | None, autore: int) -> bool:
        """Una offerta per oggetto: una nuova prende il posto della vecchia. False se l'oggetto non c'è."""
        if not 1 <= sconto_pct <= 90 or minuti < 1:
            raise ValueError("Sconto o durata non validi.")
        r = await self._pool.fetchval(
            "INSERT INTO economia_offerte (guild_id, item_id, sconto_pct, scade_at, usi_max, creata_da) "
            "SELECT $1, i.id, $3, now() + make_interval(mins => $4), $5, $6 FROM shop_items i WHERE i.id = $2 AND i.guild_id = $1 "
            "ON CONFLICT (guild_id, item_id) DO UPDATE SET sconto_pct = EXCLUDED.sconto_pct, scade_at = EXCLUDED.scade_at, "
            "usi_max = EXCLUDED.usi_max, usi = 0, creata_da = EXCLUDED.creata_da RETURNING id",
            guild_id, item_id, sconto_pct, minuti, usi_max, autore,
        )
        return r is not None

    async def offerte_attive(self, guild_id: int) -> dict[int, Offerta]:
        righe = await self._pool.fetch(
            "SELECT id, item_id, sconto_pct, scade_at, usi_max, usi FROM economia_offerte WHERE guild_id = $1 "
            "AND scade_at > now() AND (usi_max IS NULL OR usi < usi_max)", guild_id,
        )
        return {r["item_id"]: Offerta(**dict(r)) for r in righe}

    async def togli_offerta(self, guild_id: int, item_id: int) -> bool:
        r = await self._pool.execute("DELETE FROM economia_offerte WHERE guild_id = $1 AND item_id = $2", guild_id, item_id)
        return r.endswith(" 1")

    async def pulisci_offerte(self) -> int:
        r = await self._pool.execute("DELETE FROM economia_offerte WHERE scade_at < now() - interval '1 day'")
        return int(r.split()[-1])

    async def prezzo_oggi(self, guild_id: int, item) -> tuple[int, int | None]:
        """(prezzo effettivo, sconto) per lista e conferma: stessa funzione di calcolo dell'acquisto."""
        off = (await self.offerte_attive(guild_id)).get(item.id)
        return (prezzo_con_sconto(item.price, off.sconto_pct), off.sconto_pct) if off else (item.price, None)

    # ------------------------------------------------------------ ricette
    async def crea_ricetta(self, guild_id: int, nome: str, risultato: int, q: int, costo: int, ingredienti: dict[int, int]) -> str:
        """'ok', 'troppe', 'esiste', 'ingredienti', 'oggetto' (oggetto non adatto: ruolo o a elenco o di un altro server)."""
        if not 1 <= len(ingredienti) <= MAX_INGREDIENTI:
            return "ingredienti"
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                ids = [risultato, *ingredienti]
                buoni = await conn.fetchval(
                    "SELECT count(*) FROM shop_items WHERE guild_id = $1 AND id = ANY($2::int[]) AND role_id IS NULL AND NOT list_item",
                    guild_id, ids,
                )
                if buoni != len(set(ids)) or risultato in ingredienti:
                    return "oggetto"
                if await conn.fetchval("SELECT count(*) FROM economia_ricette WHERE guild_id = $1", guild_id) >= MAX_RICETTE:
                    return "troppe"
                rid = await conn.fetchval(
                    "INSERT INTO economia_ricette (guild_id, nome, risultato_item, risultato_q, costo) VALUES ($1, $2, $3, $4, $5) "
                    "ON CONFLICT DO NOTHING RETURNING id", guild_id, nome, risultato, q, costo,
                )
                if rid is None:
                    return "esiste"
                for item_id, qt in ingredienti.items():
                    await conn.execute("INSERT INTO economia_ricette_ingredienti VALUES ($1, $2, $3)", rid, item_id, qt)
                return "ok"

    async def elimina_ricetta(self, guild_id: int, nome: str) -> bool:
        r = await self._pool.execute("DELETE FROM economia_ricette WHERE guild_id = $1 AND lower(nome) = lower($2)", guild_id, nome)
        return r.endswith(" 1")

    async def ricette(self, guild_id: int) -> list[Ricetta]:
        righe = await self._pool.fetch(
            "SELECT r.id, r.nome, r.risultato_item, r.risultato_q, r.costo, "
            "(SELECT array_agg(ARRAY[g.item_id, g.quantita] ORDER BY g.item_id) FROM economia_ricette_ingredienti g WHERE g.ricetta_id = r.id) AS ing "
            "FROM economia_ricette r WHERE r.guild_id = $1 ORDER BY r.nome LIMIT 25", guild_id,
        )
        return [Ricetta(r["id"], r["nome"], r["risultato_item"], r["risultato_q"], r["costo"], tuple((a, b) for a, b in (r["ing"] or []))) for r in righe]

    async def crea_oggetto(self, guild_id: int, user_id: int, nome: str) -> EsitoRicetta:
        """
        ECO-078: toglie gli ingredienti (UPDATE `quantita >= n`, in ordine di oggetto), il costo e dà il
        risultato, tutto in una transazione: se manca qualcosa non cambia niente.
        """
        try:
            return await self._crea_oggetto(guild_id, user_id, nome)
        except _Annulla as e:
            return e.esito

    async def _crea_oggetto(self, guild_id: int, user_id: int, nome: str) -> EsitoRicetta:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                r = await conn.fetchrow(
                    "SELECT id, risultato_item, risultato_q, costo FROM economia_ricette WHERE guild_id = $1 AND lower(nome) = lower($2)",
                    guild_id, nome,
                )
                if r is None:
                    return EsitoRicetta.NON_ESISTE
                ing = await conn.fetch("SELECT item_id, quantita FROM economia_ricette_ingredienti WHERE ricetta_id = $1 ORDER BY item_id", r["id"])
                for g in ing:
                    ok = await conn.fetchval(
                        "UPDATE economia_inventario SET quantita = quantita - $4 WHERE guild_id = $1 AND user_id = $2 "
                        "AND item_id = $3 AND quantita >= $4 RETURNING 1", guild_id, user_id, g["item_id"], g["quantita"],
                    )
                    if ok is None:
                        raise _Annulla(EsitoRicetta.MANCANO)
                    await conn.execute(_PULISCI, guild_id, user_id, g["item_id"])
                if r["costo"] and not await spend_coins_in(conn, guild_id, user_id, r["costo"], "ricetta"):
                    raise _Annulla(EsitoRicetta.POCHE_MONETE)
                await conn.execute(
                    "INSERT INTO economia_inventario (guild_id, user_id, item_id, quantita) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET quantita = economia_inventario.quantita + $4",
                    guild_id, user_id, r["risultato_item"], r["risultato_q"],
                )
                return EsitoRicetta.FATTO


class _Annulla(Exception):
    def __init__(self, esito):
        self.esito = esito


def _get_pool():
    from core.database import db

    return db.pool


negozio_repo = NegozioRepository(pool_provider=_get_pool)
