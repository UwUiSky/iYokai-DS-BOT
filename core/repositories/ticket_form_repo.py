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

from core.ticket_form_logic import MAX_DOMANDE, MAX_MOTIVI, MAX_PANNELLI_PER_SERVER


async def _colonne_da_copiare(conn, tabella: str, escluse: tuple[str, ...]) -> list[str]:
    """Le colonne di una tabella (nomi dal database, mai dall'utente) tranne `escluse`: una colonna nuova si copia da sola."""
    righe = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = $1 "
        "ORDER BY ordinal_position",
        tabella,
    )
    return [r["column_name"] for r in righe if r["column_name"] not in escluse]


async def _massimo_pannelli(guild_id: int) -> int:
    from core import piani

    return await piani.limite_server_sicuro(guild_id, "pannelli_ticket")


class PannelloGiaEsistente(Exception):
    """Esiste già un pannello con questo nome nel server."""


class TroppiPannelli(Exception):
    """Il server ha già 25 pannelli."""


class TroppiMotivi(Exception):
    """Il pannello ha già 24 motivi pronti (più «Altro» fanno i 25 di un menu)."""


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
    button_style: str = "primary"  # TKT-004
    menu_segnaposto: str | None = None  # TKT-005
    embed_apertura: str | None = None  # TKT-036: nome di un embed salvato
    questionario: str | None = None  # TKT-066: la domanda dopo il voto


@dataclass(frozen=True)
class MotivoPannello:
    id: int
    panel_id: int
    posizione: int
    etichetta: str
    emoji: str | None
    testo: str | None
    descrizione: str | None = None  # TKT-005


@dataclass(frozen=True)
class DomandaModulo:
    id: int
    panel_id: int
    position: int
    label: str
    placeholder: str | None
    required: bool
    long_answer: bool
    min_length: int | None = None  # TKT-011
    max_length: int | None = None  # TKT-011
    tipo: str = "testo"  # TKT-012: testo, scelta, utente, ruolo, canale
    opzioni: tuple[str, ...] = ()
    max_valori: int = 1


def _pannello(r) -> PannelloTicket:
    return PannelloTicket(
        id=r["id"], guild_id=r["guild_id"], name=r["name"], category_id=r["category_id"],
        button_label=r["button_label"], button_emoji=r["button_emoji"],
        welcome_text=r["welcome_text"], autoclose_minutes=r["autoclose_minutes"],
        rating_enabled=r["rating_enabled"], standard_attive=r["standard_attive"],
        sollecito_minuti=r["sollecito_minuti"], ruolo_escalation=r["ruolo_escalation"],
        button_style=r["button_style"], menu_segnaposto=r["menu_segnaposto"], embed_apertura=r["embed_apertura"],
        questionario=r["questionario"],
    )


def _domanda(r) -> DomandaModulo:
    return DomandaModulo(
        id=r["id"], panel_id=r["panel_id"], position=r["position"], label=r["label"],
        placeholder=r["placeholder"], required=r["required"], long_answer=r["long_answer"],
        min_length=r["min_length"], max_length=r["max_length"], tipo=r["tipo"],
        opzioni=tuple(r["opzioni"] or ()), max_valori=r["max_valori"],
    )


def _motivo(r) -> MotivoPannello:
    return MotivoPannello(
        r["id"], r["panel_id"], r["posizione"], r["etichetta"], r["emoji"], r["testo"], r["descrizione"]
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
        massimo = await _massimo_pannelli(guild_id)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Blocco per server: due creazioni insieme non superano il tetto.
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8413, guild_id % 2**31)
                esistenti = await conn.fetchval(
                    "SELECT count(*) FROM ticket_panels WHERE guild_id = $1", guild_id
                )
                if esistenti >= massimo:
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

    async def duplica_pannello(
        self, guild_id: int, da_panel_id: int, nuovo_nome: str, categoria_id: int | None = None
    ) -> PannelloTicket:
        """CFG-044: un nuovo pannello con le stesse scelte dell'originale: domande, motivi, opzioni, accessi e risposte
        pronte approvate (senza gli usi). Poi sono indipendenti. Non si copiano ticket, trascrizioni, automazioni né il
        messaggio pubblicato. Solleva PannelloGiaEsistente, TroppiPannelli o LookupError (originale di un altro server)."""
        massimo = await _massimo_pannelli(guild_id)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8413, guild_id % 2**31)
                if await conn.fetchval("SELECT count(*) FROM ticket_panels WHERE guild_id = $1", guild_id) >= massimo:
                    raise TroppiPannelli()
                colonne = await _colonne_da_copiare(conn, "ticket_panels", ("id", "guild_id", "name", "created_at", "category_id"))
                elenco = ", ".join(colonne)
                try:
                    nuovo_id = await conn.fetchval(
                        f"INSERT INTO ticket_panels (guild_id, name, category_id{', ' + elenco if elenco else ''}) "
                        f"SELECT guild_id, $3, COALESCE($4, category_id){', ' + elenco if elenco else ''} "
                        "FROM ticket_panels WHERE id = $1 AND guild_id = $2 RETURNING id",
                        da_panel_id, guild_id, nuovo_nome, categoria_id,
                    )
                except asyncpg.UniqueViolationError as errore:
                    raise PannelloGiaEsistente() from errore
                if nuovo_id is None:
                    raise LookupError("pannello di origine non trovato")
                for tabella in ("ticket_form_questions", "ticket_panel_motivi", "ticket_panel_opzioni", "ticket_panel_accesso"):
                    cols = await _colonne_da_copiare(conn, tabella, ("id", "panel_id"))
                    lista = ", ".join(cols)
                    await conn.execute(
                        f"INSERT INTO {tabella} (panel_id, {lista}) SELECT $2, {lista} FROM {tabella} WHERE panel_id = $1",
                        da_panel_id, nuovo_id,
                    )
                await conn.execute(
                    """
                    INSERT INTO ticket_standard_replies
                        (guild_id, panel_id, title, keywords, body, attachments, status, approved_by, approved_at)
                    SELECT guild_id, $2, title, keywords, body, attachments, 'approved', approved_by, approved_at
                    FROM ticket_standard_replies WHERE panel_id = $1 AND status = 'approved'
                    """,
                    da_panel_id, nuovo_id,
                )
                riga = await conn.fetchrow("SELECT * FROM ticket_panels WHERE id = $1", nuovo_id)
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

    async def imposta_questionario(self, panel_id: int, domanda: str | None) -> bool:
        """TKT-066: la domanda che si chiede dopo il voto (None la toglie)."""
        esito = await self._pool.execute("UPDATE ticket_panels SET questionario = $2 WHERE id = $1", panel_id, domanda)
        return esito.endswith(" 1")

    async def questionario_in_attesa(self, ticket_id: int, user_id: int) -> str | None:
        """La domanda del questionario se chi ha aperto il ticket ha votato e non ha ancora risposto; altrimenti None."""
        return await self._pool.fetchval(
            """
            SELECT p.questionario FROM tickets t JOIN ticket_panels p ON p.id = t.panel_id
            WHERE t.id = $1 AND t.user_id = $2 AND t.status = 'closed' AND t.rating IS NOT NULL
              AND p.questionario IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM ticket_questionario_risposte q WHERE q.ticket_id = t.id)
            """,
            ticket_id, user_id,
        )

    async def salva_risposta_questionario(self, ticket_id: int, user_id: int, risposta: str) -> bool:
        """Una sola risposta per ticket, solo di chi lo ha aperto e dopo il voto. False se non si può (o c'è già)."""
        esito = await self._pool.execute(
            """
            INSERT INTO ticket_questionario_risposte (ticket_id, guild_id, user_id, risposta)
            SELECT t.id, t.guild_id, t.user_id, $3 FROM tickets t
            WHERE t.id = $1 AND t.user_id = $2 AND t.status = 'closed' AND t.rating IS NOT NULL
            ON CONFLICT (ticket_id) DO NOTHING
            """,
            ticket_id, user_id, risposta,
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

    async def imposta_aspetto(
        self, panel_id: int, *, button_style: str | None = None, menu_segnaposto: str | None = None,
        embed_apertura: str | None = None, azzera_embed: bool = False,
    ) -> bool:
        """TKT-004, TKT-005, TKT-036: cambia solo i valori dati (`azzera_embed` toglie l'embed di apertura)."""
        esito = await self._pool.execute(
            """
            UPDATE ticket_panels SET
                button_style = COALESCE($2, button_style),
                menu_segnaposto = COALESCE($3, menu_segnaposto),
                embed_apertura = CASE WHEN $5 THEN NULL ELSE COALESCE($4, embed_apertura) END
            WHERE id = $1
            """,
            panel_id, button_style, menu_segnaposto, embed_apertura, azzera_embed,
        )
        return esito.endswith(" 1")

    async def copia_modulo(self, da_panel_id: int, a_panel_id: int) -> int:
        """TKT-014: sostituisce le domande di `a_panel_id` con una copia di quelle di `da_panel_id`. Restituisce quante."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8414, a_panel_id)
                await conn.execute("DELETE FROM ticket_form_questions WHERE panel_id = $1", a_panel_id)
                esito = await conn.execute(
                    """
                    INSERT INTO ticket_form_questions
                        (panel_id, position, label, placeholder, required, long_answer,
                         min_length, max_length, tipo, opzioni, max_valori)
                    SELECT $2, position, label, placeholder, required, long_answer,
                           min_length, max_length, tipo, opzioni, max_valori
                    FROM ticket_form_questions WHERE panel_id = $1
                    """,
                    da_panel_id, a_panel_id,
                )
        return int(esito.split()[-1])

    # ------------------------------------------------------------ modulo
    async def elenca_domande(self, panel_id: int) -> list[DomandaModulo]:
        righe = await self._pool.fetch(
            "SELECT * FROM ticket_form_questions WHERE panel_id = $1 ORDER BY position", panel_id
        )
        return [_domanda(r) for r in righe]

    async def aggiungi_domanda(
        self, panel_id: int, label: str, placeholder: str | None = None,
        required: bool = True, long_answer: bool = False, *, min_length: int | None = None,
        max_length: int | None = None, tipo: str = "testo", opzioni: tuple[str, ...] = (), max_valori: int = 1,
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
                        (panel_id, position, label, placeholder, required, long_answer,
                         min_length, max_length, tipo, opzioni, max_valori)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *
                    """,
                    panel_id, ultima + 1, label, placeholder, required, long_answer,
                    min_length, max_length, tipo, list(opzioni), max_valori,
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

    # ------------------------------------------------------------ TKT-006 motivi pronti
    async def elenca_motivi(self, panel_id: int) -> list[MotivoPannello]:
        righe = await self._pool.fetch(
            "SELECT * FROM ticket_panel_motivi WHERE panel_id = $1 ORDER BY posizione", panel_id
        )
        return [_motivo(r) for r in righe]

    async def aggiungi_motivo(
        self, panel_id: int, etichetta: str, emoji: str | None = None, testo: str | None = None,
        descrizione: str | None = None,
    ) -> MotivoPannello:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8415, panel_id)
                ultima = await conn.fetchval(
                    "SELECT COALESCE(max(posizione), 0) FROM ticket_panel_motivi WHERE panel_id = $1", panel_id
                )
                if ultima >= MAX_MOTIVI:
                    raise TroppiMotivi()
                r = await conn.fetchrow(
                    "INSERT INTO ticket_panel_motivi (panel_id, posizione, etichetta, emoji, testo, descrizione) "
                    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
                    panel_id, ultima + 1, etichetta, emoji, testo, descrizione,
                )
        return _motivo(r)

    async def rimuovi_motivo(self, panel_id: int, posizione: int) -> bool:
        """Toglie il motivo e fa scorrere i successivi (posizioni 1..N)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                esito = await conn.execute(
                    "DELETE FROM ticket_panel_motivi WHERE panel_id = $1 AND posizione = $2", panel_id, posizione
                )
                if not esito.endswith(" 1"):
                    return False
                await conn.execute(
                    "UPDATE ticket_panel_motivi SET posizione = posizione - 1 WHERE panel_id = $1 AND posizione > $2",
                    panel_id, posizione,
                )
        return True


def _get_pool():
    from core.database import db
    return db.pool


ticket_form_repo = TicketFormRepository(pool_provider=_get_pool)
