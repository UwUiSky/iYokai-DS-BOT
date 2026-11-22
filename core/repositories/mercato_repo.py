"""
core/repositories/mercato_repo.py
=================================
Mercato tra utenti (ECO-074) e fondo premi (ECO-120). L'annuncio tiene in custodia l'oggetto; l'offerta tiene in
custodia le monete. Ogni passaggio è una transazione: l'annuncio si blocca per primo (`FOR UPDATE`), poi le righe
delle monete di tutte le persone coinvolte in ordine di ID, così due scambi incrociati non si bloccano a vicenda
e nessuno compra due volte lo stesso annuncio. Mai a se stessi; i blocchi personali (ECO-155) valgono nei due versi.
Funzioni coperte: ECO-074, ECO-120
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import asyncpg

from core.repositories.guild_chest_repo import deposit_in
from core.repositories.inventario_repo import _METTI_UNO, _PULISCI, _TOGLI_UNO
from core.repositories.leveling_repo import add_coins_in, refund_coins_in, spend_coins_in

MAX_ANNUNCI_PER_UTENTE = 5
MAX_OFFERTE_PER_ANNUNCIO = 10
GIORNI_DI_BASE = 3
GIORNI_MASSIMI = 7
REASON_DONAZIONE = "donazione_fondo"
FONDO = 0  # il «fondo premi» è l'inventario con utente 0: nessun utente vero ha questo ID


class Esito(str, Enum):
    FATTO = "fatto"
    NON_ESISTE = "non_esiste"
    SCADUTO = "scaduto"
    A_SE_STESSI = "a_se_stessi"
    BLOCCATO = "bloccato"
    POCHE_MONETE = "poche_monete"
    NON_HAI = "non_hai"
    NON_COMMERCIABILE = "non_commerciabile"
    TROPPI = "troppi"
    NON_TUO = "non_tuo"
    OFFERTA_NO = "offerta_no"


@dataclass(frozen=True)
class Annuncio:
    id: int
    venditore: int
    item_id: int
    nome: str
    quantita: int
    prezzo: int
    scade_at: datetime
    offerte: int = 0


class _Esci(Exception):
    def __init__(self, esito: Esito) -> None:
        self.esito = esito


async def _bloccato(conn: asyncpg.Connection, a: int, b: int) -> bool:
    return bool(await conn.fetchval(
        "SELECT 1 FROM economia_blocchi WHERE (user_id = $1 AND bloccato_id = $2) OR (user_id = $2 AND bloccato_id = $1)", a, b
    ))


async def _blocca_monete(conn: asyncpg.Connection, guild_id: int, utenti) -> None:
    """Le righe delle monete di tutti gli interessati, create se mancano e bloccate in ordine di ID."""
    ids = sorted({u for u in utenti if u != FONDO})
    await conn.execute(
        "INSERT INTO leveling_totals (guild_id, user_id) SELECT $1, u FROM unnest($2::bigint[]) u ON CONFLICT DO NOTHING", guild_id, ids
    )
    await conn.execute(
        "SELECT 1 FROM leveling_totals WHERE guild_id = $1 AND user_id = ANY($2::bigint[]) ORDER BY user_id FOR UPDATE", guild_id, ids
    )


async def _rendi_oggetto(conn: asyncpg.Connection, guild_id: int, utente: int, item_id: int, quantita: int) -> None:
    await conn.execute(
        "INSERT INTO economia_inventario (guild_id, user_id, item_id, quantita) VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET quantita = economia_inventario.quantita + $4",
        guild_id, utente, item_id, quantita,
    )


class MercatoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def _esegui(self, funzione) -> Esito | tuple:
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    return await funzione(conn)
        except _Esci as e:
            return e.esito

    # ---------------------------------------------------------------- annunci
    async def pubblica(self, guild_id: int, venditore: int, item_id: int, quantita: int, prezzo: int, giorni: int) -> Esito:
        """L'oggetto esce dall'inventario e resta nell'annuncio. Solo oggetti regalabili (ECO-071)."""
        if not 1 <= quantita <= 100 or not 1 <= prezzo <= 100_000_000 or not 1 <= giorni <= GIORNI_MASSIMI:
            raise ValueError("Quantità, prezzo o durata non validi.")

        async def f(conn):
            await conn.execute("SELECT pg_advisory_xact_lock($1)", venditore)
            if not await conn.fetchval("SELECT regalabile FROM shop_items WHERE id = $1 AND guild_id = $2", item_id, guild_id):
                raise _Esci(Esito.NON_COMMERCIABILE)
            if await conn.fetchval(
                "SELECT count(*) FROM economia_mercato WHERE guild_id = $1 AND venditore = $2", guild_id, venditore
            ) >= MAX_ANNUNCI_PER_UTENTE:
                raise _Esci(Esito.TROPPI)
            ok = await conn.fetchval(
                "UPDATE economia_inventario SET quantita = quantita - $4 WHERE guild_id = $1 AND user_id = $2 AND item_id = $3 "
                "AND quantita >= $4 RETURNING 1", guild_id, venditore, item_id, quantita,
            )
            if ok is None:
                raise _Esci(Esito.NON_HAI)
            await conn.execute(_PULISCI, guild_id, venditore, item_id)
            await conn.execute(
                "INSERT INTO economia_mercato (guild_id, venditore, item_id, quantita, prezzo, scade_at) "
                "VALUES ($1, $2, $3, $4, $5, now() + make_interval(days => $6))", guild_id, venditore, item_id, quantita, prezzo, giorni,
            )
            return Esito.FATTO
        return await self._esegui(f)

    async def elenco(self, guild_id: int, pagina: int = 0, per_pagina: int = 10, venditore: int | None = None) -> list[Annuncio]:
        righe = await self._pool.fetch(
            "SELECT m.id, m.venditore, m.item_id, s.name, m.quantita, m.prezzo, m.scade_at, "
            "(SELECT count(*) FROM economia_mercato_offerte o WHERE o.annuncio_id = m.id) AS offerte "
            "FROM economia_mercato m JOIN shop_items s ON s.id = m.item_id WHERE m.guild_id = $1 AND m.scade_at > now() "
            "AND ($4::bigint IS NULL OR m.venditore = $4) ORDER BY m.id DESC OFFSET $2 LIMIT $3",
            guild_id, max(0, pagina) * per_pagina, per_pagina, venditore,
        )
        return [Annuncio(r["id"], r["venditore"], r["item_id"], r["name"], r["quantita"], r["prezzo"], r["scade_at"], r["offerte"]) for r in righe]

    async def _annuncio(self, conn, guild_id: int, annuncio_id: int):
        r = await conn.fetchrow(
            "SELECT id, venditore, item_id, quantita, prezzo, scade_at < now() AS scaduto FROM economia_mercato "
            "WHERE id = $1 AND guild_id = $2 FOR UPDATE", annuncio_id, guild_id,
        )
        if r is None:
            raise _Esci(Esito.NON_ESISTE)
        return r

    async def _chiudi(self, conn, guild_id: int, a, a_chi: int | None, importo_venditore: int = 0, tieni_offerta: int | None = None) -> None:
        """
        Chiude l'annuncio: l'oggetto va a `a_chi` (o torna al venditore), le offerte (tranne `tieni_offerta`, già
        pagata al venditore) tornano agli offerenti. L'annuncio e le sue offerte sono già bloccati.
        """
        offerte = await conn.fetch("SELECT offerente, importo FROM economia_mercato_offerte WHERE annuncio_id = $1 ORDER BY offerente", a["id"])
        for o in offerte:
            if o["offerente"] != tieni_offerta:
                await refund_coins_in(conn, guild_id, o["offerente"], o["importo"])
        await conn.execute("DELETE FROM economia_mercato WHERE id = $1", a["id"])  # le offerte vanno via in cascata
        await _rendi_oggetto(conn, guild_id, a_chi if a_chi is not None else a["venditore"], a["item_id"], a["quantita"])

    async def compra(self, guild_id: int, compratore: int, annuncio_id: int) -> Esito:
        """Monete al venditore e oggetto al compratore insieme; le offerte degli altri tornano indietro."""
        async def f(conn):
            a = await self._annuncio(conn, guild_id, annuncio_id)
            if a["scaduto"]:
                raise _Esci(Esito.SCADUTO)
            if a["venditore"] == compratore:
                raise _Esci(Esito.A_SE_STESSI)
            if await _bloccato(conn, a["venditore"], compratore):
                raise _Esci(Esito.BLOCCATO)
            altri = [r["offerente"] for r in await conn.fetch("SELECT offerente FROM economia_mercato_offerte WHERE annuncio_id = $1", annuncio_id)]
            await _blocca_monete(conn, guild_id, [compratore, a["venditore"], *altri])
            if not await spend_coins_in(conn, guild_id, compratore, a["prezzo"], "mercato"):
                raise _Esci(Esito.POCHE_MONETE)
            await add_coins_in(conn, guild_id, a["venditore"], a["prezzo"], classifica=False, motivo="mercato")
            await self._chiudi(conn, guild_id, a, compratore)
            return Esito.FATTO
        return await self._esegui(f)

    async def ritira(self, guild_id: int, venditore: int, annuncio_id: int) -> Esito:
        async def f(conn):
            a = await self._annuncio(conn, guild_id, annuncio_id)
            if a["venditore"] != venditore:
                raise _Esci(Esito.NON_TUO)
            altri = [r["offerente"] for r in await conn.fetch("SELECT offerente FROM economia_mercato_offerte WHERE annuncio_id = $1", annuncio_id)]
            await _blocca_monete(conn, guild_id, [venditore, *altri])
            await self._chiudi(conn, guild_id, a, None)
            return Esito.FATTO
        return await self._esegui(f)

    async def scadenze(self, limite: int = 100) -> int:
        """Annunci scaduti: l'oggetto torna al venditore, le monete delle offerte agli offerenti."""
        chiusi = 0
        ids = [(r["id"], r["guild_id"]) for r in await self._pool.fetch(
            "SELECT id, guild_id FROM economia_mercato WHERE scade_at < now() ORDER BY id LIMIT $1", limite)]
        for annuncio_id, guild_id in ids:
            async def f(conn, annuncio_id=annuncio_id, guild_id=guild_id):
                r = await conn.fetchrow(
                    "SELECT id, venditore, item_id, quantita FROM economia_mercato WHERE id = $1 AND scade_at < now() FOR UPDATE SKIP LOCKED",
                    annuncio_id,
                )
                if r is None:
                    return Esito.NON_ESISTE
                altri = [o["offerente"] for o in await conn.fetch("SELECT offerente FROM economia_mercato_offerte WHERE annuncio_id = $1", annuncio_id)]
                await _blocca_monete(conn, guild_id, [r["venditore"], *altri])
                await self._chiudi(conn, guild_id, r, None)
                return Esito.FATTO
            if await self._esegui(f) is Esito.FATTO:
                chiusi += 1
        return chiusi

    # ---------------------------------------------------------------- offerte
    async def offri(self, guild_id: int, offerente: int, annuncio_id: int, importo: int) -> Esito:
        """L'offerta toglie subito le monete (in custodia). Una per persona: una nuova prende il posto della vecchia."""
        if importo < 1:
            raise ValueError("Offerta non valida.")

        async def f(conn):
            a = await self._annuncio(conn, guild_id, annuncio_id)
            if a["scaduto"]:
                raise _Esci(Esito.SCADUTO)
            if a["venditore"] == offerente:
                raise _Esci(Esito.A_SE_STESSI)
            if importo >= a["prezzo"]:
                raise _Esci(Esito.OFFERTA_NO)  # a quel prezzo si compra e basta
            if await _bloccato(conn, a["venditore"], offerente):
                raise _Esci(Esito.BLOCCATO)
            vecchia = await conn.fetchval("SELECT importo FROM economia_mercato_offerte WHERE annuncio_id = $1 AND offerente = $2", annuncio_id, offerente)
            if vecchia is None and await conn.fetchval(
                "SELECT count(*) FROM economia_mercato_offerte WHERE annuncio_id = $1", annuncio_id
            ) >= MAX_OFFERTE_PER_ANNUNCIO:
                raise _Esci(Esito.TROPPI)
            await _blocca_monete(conn, guild_id, [offerente])
            if vecchia is not None:
                await refund_coins_in(conn, guild_id, offerente, vecchia)
            if not await spend_coins_in(conn, guild_id, offerente, importo, "mercato_offerta"):
                raise _Esci(Esito.POCHE_MONETE)  # la transazione si annulla: anche il rimborso della vecchia
            await conn.execute(
                "INSERT INTO economia_mercato_offerte (annuncio_id, offerente, importo) VALUES ($1, $2, $3) "
                "ON CONFLICT (annuncio_id, offerente) DO UPDATE SET importo = EXCLUDED.importo", annuncio_id, offerente, importo,
            )
            return Esito.FATTO
        return await self._esegui(f)

    async def ritira_offerta(self, guild_id: int, offerente: int, annuncio_id: int) -> Esito:
        async def f(conn):
            await self._annuncio(conn, guild_id, annuncio_id)
            await _blocca_monete(conn, guild_id, [offerente])
            importo = await conn.fetchval(
                "DELETE FROM economia_mercato_offerte WHERE annuncio_id = $1 AND offerente = $2 RETURNING importo", annuncio_id, offerente
            )
            if importo is None:
                raise _Esci(Esito.OFFERTA_NO)
            await refund_coins_in(conn, guild_id, offerente, importo)
            return Esito.FATTO
        return await self._esegui(f)

    async def accetta(self, guild_id: int, venditore: int, annuncio_id: int, offerente: int) -> Esito:
        """Il venditore accetta un'offerta: le monete in custodia vanno a lui, l'oggetto all'offerente, le altre offerte tornano."""
        async def f(conn):
            a = await self._annuncio(conn, guild_id, annuncio_id)
            if a["venditore"] != venditore:
                raise _Esci(Esito.NON_TUO)
            if a["scaduto"]:
                raise _Esci(Esito.SCADUTO)
            importo = await conn.fetchval("SELECT importo FROM economia_mercato_offerte WHERE annuncio_id = $1 AND offerente = $2", annuncio_id, offerente)
            if importo is None:
                raise _Esci(Esito.OFFERTA_NO)
            altri = [r["offerente"] for r in await conn.fetch("SELECT offerente FROM economia_mercato_offerte WHERE annuncio_id = $1", annuncio_id)]
            await _blocca_monete(conn, guild_id, [venditore, *altri])
            await add_coins_in(conn, guild_id, venditore, importo, classifica=False, motivo="mercato")
            await self._chiudi(conn, guild_id, a, offerente, tieni_offerta=offerente)
            return Esito.FATTO
        return await self._esegui(f)

    async def offerte_di(self, guild_id: int, annuncio_id: int) -> list[tuple[int, int]]:
        righe = await self._pool.fetch(
            "SELECT o.offerente, o.importo FROM economia_mercato_offerte o JOIN economia_mercato m ON m.id = o.annuncio_id "
            "WHERE o.annuncio_id = $1 AND m.guild_id = $2 ORDER BY o.importo DESC LIMIT 10", annuncio_id, guild_id,
        )
        return [(r["offerente"], r["importo"]) for r in righe]

    # ---------------------------------------------------------------- fondo premi (ECO-120)
    async def dona_monete(self, guild_id: int, utente: int, importo: int) -> bool:
        """Monete dal portafoglio alla cassa del server, nella stessa transazione. False se non bastano."""
        if importo < 1:
            raise ValueError("Importo non valido.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if not await spend_coins_in(conn, guild_id, utente, importo, REASON_DONAZIONE):
                    return False
                await deposit_in(conn, guild_id, importo, REASON_DONAZIONE)
                return True

    async def dona_oggetto(self, guild_id: int, utente: int, item_id: int) -> Esito:
        """Un pezzo dal tuo inventario al fondo del server. Solo oggetti regalabili."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if not await conn.fetchval("SELECT regalabile FROM shop_items WHERE id = $1 AND guild_id = $2", item_id, guild_id):
                    return Esito.NON_COMMERCIABILE
                if await conn.fetchval(_TOGLI_UNO, guild_id, utente, item_id) is None:
                    return Esito.NON_HAI
                await conn.execute(_PULISCI, guild_id, utente, item_id)
                await conn.execute(_METTI_UNO, guild_id, FONDO, item_id)
                return Esito.FATTO

    async def fondo(self, guild_id: int) -> list[tuple[int, str, int]]:
        righe = await self._pool.fetch(
            "SELECT i.item_id, s.name, i.quantita FROM economia_inventario i JOIN shop_items s ON s.id = i.item_id AND s.guild_id = i.guild_id "
            "WHERE i.guild_id = $1 AND i.user_id = $2 ORDER BY s.name LIMIT 25", guild_id, FONDO,
        )
        return [(r["item_id"], r["name"], r["quantita"]) for r in righe]

    async def dai_dal_fondo(self, guild_id: int, a_chi: int, item_id: int) -> bool:
        """Lo staff dà un pezzo del fondo a un membro: un solo passaggio condizionato."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if await conn.fetchval(_TOGLI_UNO, guild_id, FONDO, item_id) is None:
                    return False
                await conn.execute(_PULISCI, guild_id, FONDO, item_id)
                await conn.execute(_METTI_UNO, guild_id, a_chi, item_id)
                return True


def _get_pool():
    from core.database import db

    return db.pool


mercato_repo = MercatoRepository(pool_provider=_get_pool)
