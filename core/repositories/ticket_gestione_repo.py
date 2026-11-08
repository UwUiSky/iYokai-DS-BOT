"""
core/repositories/ticket_gestione_repo.py
=========================================
Etichette dei ticket (TKT-068) e articoli della base di conoscenza (TKT-079).
Tabelle: migrazioni 0522 (`ticket_etichette`, `ticket_etichette_assegnate`) e 0525 (`ticket_articoli`).
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.ticket_gestione_logic import MAX_ARTICOLI, MAX_ETICHETTE


class TroppeEtichette(Exception):
    """Il server ha già 25 etichette."""


class EtichettaGiaEsistente(Exception):
    """Esiste già un'etichetta con questo nome."""


class TroppiArticoli(Exception):
    """Il server ha già 200 articoli."""


@dataclass(frozen=True)
class Etichetta:
    id: int
    guild_id: int
    nome: str
    colore: int
    emoji: str | None


@dataclass(frozen=True)
class Articolo:
    id: int
    guild_id: int
    titolo: str
    testo: str
    parole: str
    approvato: bool
    usi: int


def _articolo(r) -> Articolo:
    return Articolo(r["id"], r["guild_id"], r["titolo"], r["testo"], r["parole"], r["approvato"], r["usi"])


class TicketGestioneRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ etichette
    async def elenca_etichette(self, guild_id: int) -> list[Etichetta]:
        righe = await self._pool.fetch("SELECT * FROM ticket_etichette WHERE guild_id = $1 ORDER BY id", guild_id)
        return [Etichetta(r["id"], r["guild_id"], r["nome"], r["colore"], r["emoji"]) for r in righe]

    async def aggiungi_etichetta(self, guild_id: int, nome: str, colore: int, emoji: str | None) -> Etichetta:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8416, guild_id)
                if await conn.fetchval("SELECT count(*) FROM ticket_etichette WHERE guild_id = $1", guild_id) >= MAX_ETICHETTE:
                    raise TroppeEtichette()
                try:
                    r = await conn.fetchrow(
                        "INSERT INTO ticket_etichette (guild_id, nome, colore, emoji) VALUES ($1, $2, $3, $4) RETURNING *",
                        guild_id, nome, colore, emoji,
                    )
                except asyncpg.UniqueViolationError as errore:
                    raise EtichettaGiaEsistente() from errore
        return Etichetta(r["id"], r["guild_id"], r["nome"], r["colore"], r["emoji"])

    async def togli_etichetta(self, guild_id: int, nome: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM ticket_etichette WHERE guild_id = $1 AND lower(nome) = lower($2)", guild_id, nome.strip()
        )
        return esito.endswith(" 1")

    async def assegna_etichette(self, ticket_id: int, guild_id: int, etichette_ids: list[int]) -> list[Etichetta]:
        """Sostituisce le etichette del ticket. Conta solo quelle del server; restituisce quelle assegnate, nell'ordine."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM ticket_etichette_assegnate WHERE ticket_id = $1", ticket_id)
                righe = await conn.fetch(
                    "SELECT * FROM ticket_etichette WHERE guild_id = $1 AND id = ANY($2::int[]) ORDER BY id",
                    guild_id, etichette_ids,
                )
                for r in righe:
                    await conn.execute(
                        "INSERT INTO ticket_etichette_assegnate (ticket_id, etichetta_id) VALUES ($1, $2)", ticket_id, r["id"]
                    )
        return [Etichetta(r["id"], r["guild_id"], r["nome"], r["colore"], r["emoji"]) for r in righe]

    async def etichette_del_ticket(self, ticket_id: int) -> list[Etichetta]:
        righe = await self._pool.fetch(
            "SELECT e.* FROM ticket_etichette e JOIN ticket_etichette_assegnate a ON a.etichetta_id = e.id "
            "WHERE a.ticket_id = $1 ORDER BY e.id", ticket_id,
        )
        return [Etichetta(r["id"], r["guild_id"], r["nome"], r["colore"], r["emoji"]) for r in righe]

    # ------------------------------------------------------------ articoli
    async def salva_articolo(
        self, guild_id: int, titolo: str, testo: str, parole: str, autore: int, articolo_id: int | None = None
    ) -> Articolo | None:
        """Nuovo articolo (None se il server è al tetto) o modifica di uno esistente (None se non è di questo server)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if articolo_id is not None:
                    r = await conn.fetchrow(
                        "UPDATE ticket_articoli SET titolo = $3, testo = $4, parole = $5 WHERE id = $1 AND guild_id = $2 RETURNING *",
                        articolo_id, guild_id, titolo, testo, parole,
                    )
                    return _articolo(r) if r else None
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8417, guild_id)
                if await conn.fetchval("SELECT count(*) FROM ticket_articoli WHERE guild_id = $1", guild_id) >= MAX_ARTICOLI:
                    raise TroppiArticoli()
                r = await conn.fetchrow(
                    "INSERT INTO ticket_articoli (guild_id, titolo, testo, parole, creato_da) "
                    "VALUES ($1, $2, $3, $4, $5) RETURNING *",
                    guild_id, titolo, testo, parole, autore,
                )
        return _articolo(r)

    async def articolo(self, guild_id: int, articolo_id: int) -> Articolo | None:
        r = await self._pool.fetchrow("SELECT * FROM ticket_articoli WHERE id = $1 AND guild_id = $2", articolo_id, guild_id)
        return _articolo(r) if r else None

    async def cerca_articoli(self, guild_id: int, testo: str = "", limite: int = 25, solo_approvati: bool = False) -> list[Articolo]:
        righe = await self._pool.fetch(
            "SELECT * FROM ticket_articoli WHERE guild_id = $1 AND ($4 OR approvato) AND ($2 = '' OR titolo ILIKE '%' || $2 || '%') "
            "ORDER BY usi DESC, id LIMIT $3",
            guild_id, testo.replace("%", "").replace("_", "").strip(), limite, not solo_approvati,
        )
        return [_articolo(r) for r in righe]

    async def tutti_gli_approvati(self, guild_id: int) -> list[Articolo]:
        return await self.cerca_articoli(guild_id, "", MAX_ARTICOLI, solo_approvati=True)

    async def elimina_articolo(self, guild_id: int, articolo_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM ticket_articoli WHERE id = $1 AND guild_id = $2", articolo_id, guild_id)
        return esito.endswith(" 1")

    async def conta_uso(self, articolo_id: int) -> None:
        await self._pool.execute("UPDATE ticket_articoli SET usi = usi + 1 WHERE id = $1", articolo_id)


def _get_pool():
    from core.database import db
    return db.pool


ticket_gestione_repo = TicketGestioneRepository(pool_provider=_get_pool)
