"""
core/repositories/shop_repo.py
==================================
Shop dell'economia: catalogo degli oggetti per server (prezzo, ruolo
facoltativo) e acquisti. L'acquisto toglie i coin e registra la riga
nella stessa transazione; un oggetto a ruolo si compra una volta sola
per utente (indice unico, migrazione 0015).
Oltre al prezzo: scorte, ruolo richiesto, ordine, categoria, testo di
risposta, ruolo a tempo e oggetti «a elenco» (una riga diversa a ogni
acquisto).
Funzioni coperte: SPEC §15.4
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import asyncpg

from core.repositories.leveling_repo import refund_coins_in, spend_coins_in


@dataclass(frozen=True)
class ShopItem:
    id: int
    guild_id: int
    name: str
    price: int
    role_id: int | None
    description: str | None
    stock: int | None = None  # None = scorte illimitate
    required_role_id: int | None = None  # chi non ce l'ha non compra
    sort_order: int = 0  # ECO-065: in lista prima i numeri bassi
    category: str | None = None  # ECO-066
    reply_text: str | None = None  # ECO-068: detto a chi compra
    role_duration_hours: int | None = None  # ECO-063: il ruolo comprato scade dopo tante ore
    list_item: bool = False  # ECO-067: ogni acquisto consegna una riga
    lines_left: int | None = None  # righe ancora da consegnare (solo oggetti a elenco)


@dataclass(frozen=True)
class Purchase:
    id: int
    guild_id: int
    user_id: int
    item_id: int
    purchased_at: datetime


class EsitoAcquisto(str, Enum):
    RIUSCITO = "riuscito"
    GIA_ACQUISTATO = "gia_acquistato"
    SALDO_INSUFFICIENTE = "saldo_insufficiente"
    ESAURITO = "esaurito"
    PREZZO_CAMBIATO = "prezzo_cambiato"


@dataclass(frozen=True)
class Acquisto:
    esito: EsitoAcquisto
    purchase_id: int | None = None
    riga: str | None = None  # oggetto a elenco: la riga consegnata
    ruolo_scade_il: datetime | None = None  # ruolo a tempo: quando finisce


class _SaldoInsufficiente(Exception):
    """Interna a buy_item: annulla la transazione dell'acquisto."""


class _Esaurito(Exception):
    """Interna a buy_item: le scorte sono finite, annulla la transazione."""


class _PrezzoCambiato(Exception):
    """Interna a buy_item: il prezzo non è più quello che l'utente ha confermato."""


_CAMPI_MODIFICABILI = (
    "name", "price", "description", "stock", "required_role_id",
    "sort_order", "category", "reply_text", "role_duration_hours",
)
MAX_NOME = 80
MAX_CATEGORIA = 30
MAX_RISPOSTA = 500
MAX_ORE_RUOLO = 24 * 365
MAX_POSIZIONE = 9999
MAX_RIGHE_PER_OGGETTO = 1000
MAX_LUNGHEZZA_RIGA = 200
MAX_TENTATIVI_SCADENZA = 5
MAX_PREZZO = 1_000_000
MAX_ID_OGGETTO = 2_147_483_647  # SERIAL di Postgres


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS shop_items (
            id            SERIAL PRIMARY KEY,
            guild_id      BIGINT NOT NULL,
            name          TEXT NOT NULL,
            price         INTEGER NOT NULL,
            role_id       BIGINT,
            description   TEXT
        );

        CREATE TABLE IF NOT EXISTS shop_purchases (
            id             SERIAL PRIMARY KEY,
            guild_id       BIGINT NOT NULL,
            user_id        BIGINT NOT NULL,
            item_id        INTEGER NOT NULL,
            purchased_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_shop_items_guild ON shop_items (guild_id);
        CREATE INDEX IF NOT EXISTS idx_shop_purchases_user
            ON shop_purchases (guild_id, user_id, item_id);
        """
    )


class ShopRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_item(self, row) -> ShopItem:
        return ShopItem(
            id=row["id"],
            guild_id=row["guild_id"],
            name=row["name"],
            price=row["price"],
            role_id=row["role_id"],
            description=row["description"],
            stock=row["stock"],
            required_role_id=row["required_role_id"],
            sort_order=row["sort_order"],
            category=row["category"],
            reply_text=row["reply_text"],
            role_duration_hours=row["role_duration_hours"],
            list_item=row["list_item"],
            lines_left=row["lines_left"] if "lines_left" in row else None,
        )

    async def add_item(
        self,
        guild_id: int,
        name: str,
        price: int,
        role_id: int | None = None,
        description: str | None = None,
        stock: int | None = None,
        required_role_id: int | None = None,
        sort_order: int = 0,
        category: str | None = None,
        reply_text: str | None = None,
        role_duration_hours: int | None = None,
        list_item: bool = False,
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Il nome non può essere vuoto né di soli spazi.")
        _controlla_campi_catalogo(
            sort_order=sort_order, category=category, reply_text=reply_text,
            role_duration_hours=role_duration_hours,
        )
        row = await self._pool.fetchrow(
            """
            INSERT INTO shop_items (guild_id, name, price, role_id, description, stock,
                                    required_role_id, sort_order, category, reply_text,
                                    role_duration_hours, list_item)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            guild_id,
            name,
            price,
            role_id,
            description,
            stock,
            required_role_id,
            sort_order,
            (category or "").strip() or None,
            (reply_text or "").strip() or None,
            role_duration_hours,
            list_item,
        )
        return row["id"]

    async def update_item(self, item_id: int, guild_id: int, **campi) -> ShopItem | None:
        """
        Cambia solo i campi dati (name, price, description, stock,
        required_role_id; `None` toglie descrizione, scorte o ruolo). I
        prezzi nuovi valgono per gli acquisti futuri. None se l'oggetto non
        esiste in quel server; ValueError per campi o valori non validi.
        """
        for nome, valore in campi.items():
            if nome not in _CAMPI_MODIFICABILI:
                raise ValueError(f"Campo non modificabile: {nome}")
            if nome == "name":
                valore = valore.strip() if valore else ""
                if not (valore and len(valore) <= MAX_NOME):
                    raise ValueError(f"Il nome deve avere da 1 a {MAX_NOME} caratteri (non solo spazi).")
                campi[nome] = valore
            if nome == "price" and not (1 <= valore <= MAX_PREZZO):
                raise ValueError(f"Il prezzo deve stare tra 1 e {MAX_PREZZO}.")
            if nome == "stock" and valore is not None and valore < 0:
                raise ValueError("Le scorte non possono essere negative.")
            if nome in ("sort_order", "category", "reply_text", "role_duration_hours"):
                _controlla_campi_catalogo(**{nome: valore})
                if nome in ("category", "reply_text"):
                    campi[nome] = (valore or "").strip() or None
        if not campi:
            return await self.get_item(item_id, guild_id)
        if not 1 <= item_id <= MAX_ID_OGGETTO:
            return None
        assegnazioni = ", ".join(f"{nome} = ${i + 3}" for i, nome in enumerate(campi))
        riga = await self._pool.fetchrow(
            f"UPDATE shop_items SET {assegnazioni} WHERE id = $1 AND guild_id = $2 RETURNING *",
            item_id,
            guild_id,
            *campi.values(),
        )
        return self._row_to_item(riga) if riga is not None else None

    async def remove_item(self, item_id: int, guild_id: int) -> bool:
        if not 1 <= item_id <= MAX_ID_OGGETTO:
            return False
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.execute(
                    "DELETE FROM shop_items WHERE id = $1 AND guild_id = $2", item_id, guild_id
                )
                if not result.endswith(" 1"):
                    return False
                await conn.execute(
                    "DELETE FROM shop_item_lines WHERE item_id = $1 AND guild_id = $2",
                    item_id, guild_id,
                )
                return True

    # Le righe ancora libere di un oggetto a elenco (None per gli altri).
    _SELECT_OGGETTO = """
        SELECT i.*,
               CASE WHEN i.list_item THEN (
                   SELECT count(*) FROM shop_item_lines l
                   WHERE l.item_id = i.id AND l.delivered_at IS NULL
               ) END AS lines_left
        FROM shop_items i
    """

    async def list_items(self, guild_id: int, categoria: str | None = None) -> list[ShopItem]:
        """In ordine: categoria (prima gli oggetti senza), posizione, prezzo, ID."""
        rows = await self._pool.fetch(
            self._SELECT_OGGETTO
            + " WHERE i.guild_id = $1 AND ($2::text IS NULL OR lower(i.category) = lower($2))"
            " ORDER BY (i.category IS NOT NULL), lower(i.category), i.sort_order, i.price, i.id",
            guild_id,
            (categoria or "").strip() or None,
        )
        return [self._row_to_item(r) for r in rows]

    async def get_item(self, item_id: int, guild_id: int) -> ShopItem | None:
        if not 1 <= item_id <= MAX_ID_OGGETTO:
            return None
        row = await self._pool.fetchrow(
            self._SELECT_OGGETTO + " WHERE i.id = $1 AND i.guild_id = $2", item_id, guild_id
        )
        return self._row_to_item(row) if row is not None else None

    async def add_lines(self, item_id: int, guild_id: int, righe: list[str]) -> int | None:
        """
        ECO-067: aggiunge righe da consegnare e rende l'oggetto «a elenco».
        Righe vuote scartate; al massimo MAX_RIGHE_PER_OGGETTO libere per oggetto.
        Restituisce quante ne ha aggiunte, None se l'oggetto non esiste.
        """
        pulite = [r.strip() for r in righe if r.strip()]
        if any(len(r) > MAX_LUNGHEZZA_RIGA for r in pulite):
            raise ValueError(f"Ogni riga può avere al massimo {MAX_LUNGHEZZA_RIGA} caratteri.")
        if not 1 <= item_id <= MAX_ID_OGGETTO:
            return None
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                esiste = await conn.fetchval(
                    "SELECT id FROM shop_items WHERE id = $1 AND guild_id = $2 FOR UPDATE",
                    item_id, guild_id,
                )
                if esiste is None:
                    return None
                libere = await conn.fetchval(
                    "SELECT count(*) FROM shop_item_lines WHERE item_id = $1 AND delivered_at IS NULL",
                    item_id,
                )
                if libere + len(pulite) > MAX_RIGHE_PER_OGGETTO:
                    raise ValueError(
                        f"Un oggetto può avere al massimo {MAX_RIGHE_PER_OGGETTO} righe da consegnare."
                    )
                await conn.executemany(
                    "INSERT INTO shop_item_lines (guild_id, item_id, line) VALUES ($1, $2, $3)",
                    [(guild_id, item_id, r) for r in pulite],
                )
                await conn.execute("UPDATE shop_items SET list_item = true WHERE id = $1", item_id)
                return len(pulite)

    async def buy_item(
        self, guild_id: int, user_id: int, item: ShopItem, prezzo_atteso: int | None = None
    ) -> Acquisto:
        """
        `prezzo_atteso` (acquisto confermato): se il prezzo di oggi, letto nella
        transazione, è diverso da quello che l'utente ha visto, non si compra.
        Registra l'acquisto e toglie i coin in UNA transazione (BUG-14).
        Un oggetto a ruolo già comprato non si ricompra: lo decide
        l'indice unico, non una lettura fatta prima. Se il saldo non
        basta non resta scritto nulla.
        """
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    purchase_id = await conn.fetchval(
                        """
                        INSERT INTO shop_purchases (guild_id, user_id, item_id, role_id)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (guild_id, user_id, item_id) WHERE role_id IS NOT NULL
                            DO NOTHING
                        RETURNING id
                        """,
                        guild_id,
                        user_id,
                        item.id,
                        item.role_id,
                    )
                    if purchase_id is None:
                        return Acquisto(EsitoAcquisto.GIA_ACQUISTATO)
                    # Scorte: scendono qui, nella stessa transazione, prima dei coin
                    # (stesso ordine del rimborso: nessuno stallo). Senza scorte
                    # (stock NULL) la riga si lascia com'è.
                    # RETURNING price: il prezzo di adesso, con la riga bloccata fino
                    # alla fine della transazione (una modifica del prezzo aspetta).
                    riga_oggetto = await conn.fetchrow(
                        "UPDATE shop_items SET stock = CASE WHEN stock IS NULL THEN NULL ELSE stock - 1 END "
                        "WHERE id = $1 AND guild_id = $2 AND (stock IS NULL OR stock > 0) "
                        "RETURNING price, list_item, role_duration_hours",
                        item.id,
                        guild_id,
                    )
                    if riga_oggetto is None:
                        raise _Esaurito
                    prezzo = riga_oggetto["price"]
                    if prezzo_atteso is not None and prezzo != prezzo_atteso:
                        raise _PrezzoCambiato
                    # Oggetto a elenco: la riga si prende qui (la riga dell'oggetto è
                    # bloccata, quindi due acquisti insieme prendono righe diverse).
                    riga = None
                    if riga_oggetto["list_item"]:
                        riga = await conn.fetchval(
                            "UPDATE shop_item_lines SET buyer_id = $2, purchase_id = $3, delivered_at = now() "
                            "WHERE id = (SELECT id FROM shop_item_lines WHERE item_id = $1 "
                            "AND delivered_at IS NULL ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) "
                            "RETURNING line",
                            item.id, user_id, purchase_id,
                        )
                        if riga is None:
                            raise _Esaurito
                    if not await spend_coins_in(conn, guild_id, user_id, prezzo):
                        raise _SaldoInsufficiente
                    scade = None
                    if item.role_id is not None and riga_oggetto["role_duration_hours"]:
                        scade = await conn.fetchval(
                            "UPDATE shop_purchases SET role_expires_at = "
                            "now() + make_interval(hours => $2) WHERE id = $1 "
                            "RETURNING role_expires_at",
                            purchase_id, riga_oggetto["role_duration_hours"],
                        )
                    return Acquisto(EsitoAcquisto.RIUSCITO, purchase_id, riga, scade)
        except _Esaurito:
            return Acquisto(EsitoAcquisto.ESAURITO)
        except _PrezzoCambiato:
            return Acquisto(EsitoAcquisto.PREZZO_CAMBIATO)
        except _SaldoInsufficiente:
            return Acquisto(EsitoAcquisto.SALDO_INSUFFICIENTE)

    async def refund_purchase(
        self, purchase_id: int, guild_id: int, user_id: int, price: int
    ) -> bool:
        """
        Annulla un acquisto appena fatto (il ruolo non è stato dato):
        cancella la riga e restituisce i coin nella stessa transazione.
        Chiamarla due volte rimborsa una volta sola.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                cancellato = await conn.fetchrow(
                    "DELETE FROM shop_purchases WHERE id = $1 RETURNING id, item_id", purchase_id
                )
                if cancellato is None:
                    return False
                # Prima le scorte, poi i coin: lo stesso ordine dell'acquisto.
                await conn.execute(
                    "UPDATE shop_items SET stock = stock + 1 WHERE id = $1 AND stock IS NOT NULL",
                    cancellato["item_id"],
                )
                # Oggetto a elenco: la riga torna libera per un altro.
                await conn.execute(
                    "UPDATE shop_item_lines SET buyer_id = NULL, purchase_id = NULL, delivered_at = NULL "
                    "WHERE purchase_id = $1",
                    purchase_id,
                )
                await refund_coins_in(conn, guild_id, user_id, price)
                return True

    # ------------------------------------------------------------------
    # Ruolo a tempo (ECO-063)
    # ------------------------------------------------------------------
    async def list_expired_roles(self, limite: int = 100) -> list[dict]:
        """Acquisti con il ruolo scaduto, da togliere (id, guild_id, user_id, role_id, expiry_attempts)."""
        rows = await self._pool.fetch(
            "SELECT id, guild_id, user_id, role_id, expiry_attempts FROM shop_purchases "
            "WHERE role_expires_at IS NOT NULL AND role_expires_at <= now() AND role_id IS NOT NULL "
            "ORDER BY role_expires_at LIMIT $1",
            limite,
        )
        return [dict(r) for r in rows]

    async def close_role_purchase(self, purchase_id: int) -> None:
        """Ruolo tolto (o non più rimovibile): l'acquisto resta nello storico e si può ricomprare."""
        await self._pool.execute(
            "UPDATE shop_purchases SET role_id = NULL, role_expires_at = NULL WHERE id = $1",
            purchase_id,
        )

    async def note_expiry_failure(self, purchase_id: int) -> int:
        """Un tentativo di togliere il ruolo è fallito: restituisce quanti ne sono falliti."""
        return await self._pool.fetchval(
            "UPDATE shop_purchases SET expiry_attempts = expiry_attempts + 1 "
            "WHERE id = $1 RETURNING expiry_attempts",
            purchase_id,
        )


def _controlla_campi_catalogo(
    sort_order=None, category=None, reply_text=None, role_duration_hours=None
) -> None:
    if sort_order is not None and not 0 <= sort_order <= MAX_POSIZIONE:
        raise ValueError(f"La posizione deve stare tra 0 e {MAX_POSIZIONE}.")
    if category is not None and len(category.strip()) > MAX_CATEGORIA:
        raise ValueError(f"La categoria può avere al massimo {MAX_CATEGORIA} caratteri.")
    if reply_text is not None and len(reply_text.strip()) > MAX_RISPOSTA:
        raise ValueError(f"Il testo di risposta può avere al massimo {MAX_RISPOSTA} caratteri.")
    if role_duration_hours is not None and not 1 <= role_duration_hours <= MAX_ORE_RUOLO:
        raise ValueError(f"La durata del ruolo deve stare tra 1 e {MAX_ORE_RUOLO} ore.")


def _get_pool():
    from core.database import db
    return db.pool


shop_repo = ShopRepository(pool_provider=_get_pool)
