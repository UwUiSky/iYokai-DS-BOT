"""
core/repositories/ticket_form_repo.py
=====================================
Pannelli dei ticket (più per server) e domande del modulo di ciascuno.
Funzioni coperte: SPEC §22 (NF-13)
Tabelle: migrazione 0100 (`ticket_panels`, `ticket_form_questions`).
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.ticket_form_logic import MAX_DOMANDE, MAX_PANNELLI_PER_SERVER


class PannelloGiaEsistente(Exception):
    """Esiste già un pannello con questo nome nel server."""


class TroppiPannelli(Exception):
    """Il server ha già 25 pannelli."""


class TroppeDomande(Exception):
    """Il modulo ha già 5 domande (limite di Discord)."""


@dataclass(frozen=True)
class PannelloTicket:
    id: int
    guild_id: int
    name: str
    category_id: int
    button_label: str
    button_emoji: str | None
    welcome_text: str | None
    autoclose_minutes: int | None
    rating_enabled: bool
    standard_attive: bool = False
    sollecito_minuti: int | None = None
    ruolo_escalation: int | None = None


@dataclass(frozen=True)
class DomandaModulo:
    id: int
    panel_id: int
    position: int
    label: str
    placeholder: str | None
    required: bool
    long_answer: bool


def _pannello(r) -> PannelloTicket:
    return PannelloTicket(
        id=r["id"], guild_id=r["guild_id"], name=r["name"], category_id=r["category_id"],
        button_label=r["button_label"], button_emoji=r["button_emoji"],
        welcome_text=r["welcome_text"], autoclose_minutes=r["autoclose_minutes"],
        rating_enabled=r["rating_enabled"], standard_attive=r["standard_attive"],
        sollecito_minuti=r["sollecito_minuti"], ruolo_escalation=r["ruolo_escalation"],
    )


def _domanda(r) -> DomandaModulo:
    return DomandaModulo(
        id=r["id"], panel_id=r["panel_id"], position=r["position"], label=r["label"],
        placeholder=r["placeholder"], required=r["required"], long_answer=r["long_answer"],
    )


class TicketFormRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ pannelli
    async def crea_pannello(
        self, guild_id: int, name: str, category_id: int, button_label: str,
        button_emoji: str | None = None, welcome_text: str | None = None,
    ) -> PannelloTicket:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Blocco per server: due creazioni insieme non superano il tetto.
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8413, guild_id % 2**31)
                esistenti = await conn.fetchval(
                    "SELECT count(*) FROM ticket_panels WHERE guild_id = $1", guild_id
                )
                if esistenti >= MAX_PANNELLI_PER_SERVER:
                    raise TroppiPannelli()
                try:
                    riga = await conn.fetchrow(
                        """
                        INSERT INTO ticket_panels
                            (guild_id, name, category_id, button_label, button_emoji, welcome_text)
                        VALUES ($1, $2, $3, $4, $5, $6) RETURNING *
                        """,
                        guild_id, name, category_id, button_label, button_emoji, welcome_text,
                    )
                except asyncpg.UniqueViolationError as errore:
                    raise PannelloGiaEsistente() from errore
        return _pannello(riga)

    async def elenca_pannelli(self, guild_id: int) -> list[PannelloTicket]:
        righe = await self._pool.fetch(
            "SELECT * FROM ticket_panels WHERE guild_id = $1 ORDER BY id", guild_id
        )
        return [_pannello(r) for r in righe]

    async def pannello_per_id(self, panel_id: int) -> PannelloTicket | None:
        r = await self._pool.fetchrow("SELECT * FROM ticket_panels WHERE id = $1", panel_id)
        return _pannello(r) if r else None

    async def pannello_per_nome(self, guild_id: int, name: str) -> PannelloTicket | None:
        r = await self._pool.fetchrow(
            "SELECT * FROM ticket_panels WHERE guild_id = $1 AND lower(name) = lower($2)",
            guild_id, name,
        )
        return _pannello(r) if r else None

    async def rimuovi_pannello(self, guild_id: int, name: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM ticket_panels WHERE guild_id = $1 AND lower(name) = lower($2)",
            guild_id, name,
        )
        return esito.endswith(" 1")

    async def imposta_chiusura_automatica(self, panel_id: int, minuti: int | None) -> bool:
        esito = await self._pool.execute(
            "UPDATE ticket_panels SET autoclose_minutes = $2 WHERE id = $1", panel_id, minuti
        )
        return esito.endswith(" 1")

    async def imposta_voto(self, panel_id: int, attivo: bool) -> bool:
        esito = await self._pool.execute(
            "UPDATE ticket_panels SET rating_enabled = $2 WHERE id = $1", panel_id, attivo
        )
        return esito.endswith(" 1")

    async def imposta_standard(self, panel_id: int, attive: bool) -> bool:
        """#139: risposte standard accese o spente per il pannello."""
        esito = await self._pool.execute(
            "UPDATE ticket_panels SET standard_attive = $2 WHERE id = $1", panel_id, attive
        )
        return esito.endswith(" 1")

    async def imposta_sollecito(self, panel_id: int, minuti: int | None, ruolo_id: int | None) -> bool:
        """#139: dopo `minuti` senza risposta dello staff il bot chiede all'utente; `ruolo_id` è chi chiamare."""
        esito = await self._pool.execute(
            "UPDATE ticket_panels SET sollecito_minuti = $2, ruolo_escalation = $3 WHERE id = $1",
            panel_id, minuti, ruolo_id,
        )
        return esito.endswith(" 1")

    # ------------------------------------------------------------ modulo
    async def elenca_domande(self, panel_id: int) -> list[DomandaModulo]:
        righe = await self._pool.fetch(
            "SELECT * FROM ticket_form_questions WHERE panel_id = $1 ORDER BY position", panel_id
        )
        return [_domanda(r) for r in righe]

    async def aggiungi_domanda(
        self, panel_id: int, label: str, placeholder: str | None = None,
        required: bool = True, long_answer: bool = False,
    ) -> DomandaModulo:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8414, panel_id)
                ultima = await conn.fetchval(
                    "SELECT COALESCE(max(position), 0) FROM ticket_form_questions WHERE panel_id = $1",
                    panel_id,
                )
                if ultima >= MAX_DOMANDE:
                    raise TroppeDomande()
                riga = await conn.fetchrow(
                    """
                    INSERT INTO ticket_form_questions
                        (panel_id, position, label, placeholder, required, long_answer)
                    VALUES ($1, $2, $3, $4, $5, $6) RETURNING *
                    """,
                    panel_id, ultima + 1, label, placeholder, required, long_answer,
                )
        return _domanda(riga)

    async def rimuovi_domanda(self, panel_id: int, position: int) -> bool:
        """Toglie la domanda e fa scorrere le successive, così le posizioni restano 1..N."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                esito = await conn.execute(
                    "DELETE FROM ticket_form_questions WHERE panel_id = $1 AND position = $2",
                    panel_id, position,
                )
                if not esito.endswith(" 1"):
                    return False
                await conn.execute(
                    "UPDATE ticket_form_questions SET position = position - 1 "
                    "WHERE panel_id = $1 AND position > $2",
                    panel_id, position,
                )
        return True


def _get_pool():
    from core.database import db
    return db.pool


ticket_form_repo = TicketFormRepository(pool_provider=_get_pool)
