"""
core/repositories/eventi_repo.py
================================
Archivio degli eventi con iscrizioni: evento, iscritti (si, forse, attesa). Ogni iscrizione, uscita e modifica dei posti
gira sotto un blocco per evento: i posti non si superano mai e la lista d'attesa scorre in ordine di arrivo.
Tabelle: core/migrations/0561_eventi.sql.
Funzioni coperte: catalogo #128 UTL-113 (D69, B24)
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

_COLONNE = ("id, guild_id, channel_id, message_id, autore_id, titolo, descrizione, quando, posti, ruolo_ping_id, "
            "discord_event_id, stato")


class EventiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    @staticmethod
    async def _blocco(conn, evento_id: int) -> None:
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('evento'), $1)", evento_id % 2**31)

    async def crea(self, guild_id: int, channel_id: int, autore_id: int, titolo: str, descrizione: str, quando: datetime,
                   posti: int | None, ruolo_ping_id: int | None) -> int:
        return await self._pool.fetchval(
            "INSERT INTO eventi (guild_id, channel_id, autore_id, titolo, descrizione, quando, posti, ruolo_ping_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id",
            guild_id, channel_id, autore_id, titolo, descrizione, quando, posti, ruolo_ping_id)

    async def prendi(self, evento_id: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow(f"SELECT {_COLONNE} FROM eventi WHERE id = $1", evento_id)

    async def imposta_messaggio(self, evento_id: int, message_id: int) -> None:
        await self._pool.execute("UPDATE eventi SET message_id = $2 WHERE id = $1", evento_id, message_id)

    async def imposta_evento_discord(self, evento_id: int, discord_event_id: int | None) -> None:
        await self._pool.execute("UPDATE eventi SET discord_event_id = $2 WHERE id = $1", evento_id, discord_event_id)

    async def elimina(self, evento_id: int) -> None:
        await self._pool.execute("DELETE FROM eventi WHERE id = $1", evento_id)

    async def elimina_del_canale(self, guild_id: int, channel_id: int) -> int:
        r = await self._pool.execute("DELETE FROM eventi WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id)
        return int(r.split()[-1])

    async def elenco(self, guild_id: int, adesso: datetime, autore_id: int | None = None, limite: int = 25) -> list[asyncpg.Record]:
        """Gli eventi attivi che non sono ancora iniziati, i più vicini prima."""
        return await self._pool.fetch(
            f"SELECT {_COLONNE} FROM eventi WHERE guild_id = $1 AND stato = 'attivo' AND quando > $2 "
            "AND ($3::bigint IS NULL OR autore_id = $3) ORDER BY quando LIMIT $4", guild_id, adesso, autore_id, limite)

    async def cerca(self, guild_id: int, testo: str, adesso: datetime, limite: int = 25) -> list[asyncpg.Record]:
        pulito = testo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return await self._pool.fetch(
            "SELECT id, titolo, quando FROM eventi WHERE guild_id = $1 AND stato = 'attivo' AND quando > $2 "
            "AND titolo ILIKE $3 ORDER BY quando LIMIT $4", guild_id, adesso, f"%{pulito}%", limite)

    async def conta_aperti(self, guild_id: int, autore_id: int, adesso: datetime) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM eventi WHERE guild_id = $1 AND autore_id = $2 AND stato = 'attivo' AND quando > $3",
            guild_id, autore_id, adesso)

    # --- iscrizioni -------------------------------------------------------------------------------------------------
    async def _riequilibra(self, conn, evento_id: int, posti: int | None) -> list[int]:
        """Porta dalla lista d'attesa ai «si» finché c'è posto. Torna chi è stato promosso, in ordine."""
        if not posti:
            tutti = await conn.fetch(
                "UPDATE eventi_iscritti SET stato = 'si' WHERE evento_id = $1 AND stato = 'attesa' RETURNING user_id", evento_id)
            return [r["user_id"] for r in tutti]
        promossi: list[int] = []
        liberi = posti - await conn.fetchval("SELECT count(*) FROM eventi_iscritti WHERE evento_id = $1 AND stato = 'si'", evento_id)
        if liberi > 0:
            righe = await conn.fetch(
                "UPDATE eventi_iscritti SET stato = 'si' WHERE (evento_id, user_id) IN "
                "(SELECT evento_id, user_id FROM eventi_iscritti WHERE evento_id = $1 AND stato = 'attesa' ORDER BY dal LIMIT $2) "
                "RETURNING user_id, dal", evento_id, liberi)
            promossi = [r["user_id"] for r in sorted(righe, key=lambda r: r["dal"])]
        return promossi

    async def iscriviti(self, evento_id: int, user_id: int, scelta: str, adesso: datetime) -> tuple[str, str | None, list[int]]:
        """scelta: «si», «forse», «esco». Torna (esito, stato dell'utente, promossi). Esiti: «ok», «uguale», «chiuso»,
        «niente» (esco senza essere iscritto). Lo stato è «si», «forse», «attesa» o None."""
        async with self._pool.acquire() as conn, conn.transaction():
            await self._blocco(conn, evento_id)
            e = await conn.fetchrow("SELECT guild_id, posti, stato, quando FROM eventi WHERE id = $1", evento_id)
            if e is None or e["stato"] != "attivo" or e["quando"] <= adesso:
                return "chiuso", None, []
            prima = await conn.fetchval("SELECT stato FROM eventi_iscritti WHERE evento_id = $1 AND user_id = $2", evento_id, user_id)
            if scelta == "esco":
                if prima is None:
                    return "niente", None, []
                await conn.execute("DELETE FROM eventi_iscritti WHERE evento_id = $1 AND user_id = $2", evento_id, user_id)
                return "ok", None, await self._riequilibra(conn, evento_id, e["posti"])
            if scelta == "si":
                if prima in ("si", "attesa"):
                    return "uguale", prima, []
                occupati = await conn.fetchval("SELECT count(*) FROM eventi_iscritti WHERE evento_id = $1 AND stato = 'si'", evento_id)
                nuovo = "attesa" if e["posti"] and occupati >= e["posti"] else "si"
            else:
                if prima == "forse":
                    return "uguale", prima, []
                nuovo = "forse"
            await conn.execute(
                "INSERT INTO eventi_iscritti (evento_id, guild_id, user_id, stato) VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (evento_id, user_id) DO UPDATE SET stato = EXCLUDED.stato, dal = clock_timestamp()",
                evento_id, e["guild_id"], user_id, nuovo)
            return "ok", nuovo, await self._riequilibra(conn, evento_id, e["posti"])

    async def conteggi(self, evento_id: int) -> dict[str, int]:
        righe = await self._pool.fetch("SELECT stato, count(*) AS n FROM eventi_iscritti WHERE evento_id = $1 GROUP BY stato", evento_id)
        fuori = {"si": 0, "forse": 0, "attesa": 0}
        fuori.update({r["stato"]: r["n"] for r in righe})
        return fuori

    async def iscritti(self, evento_id: int, stato: str, limite: int, scarto: int = 0) -> list[int]:
        righe = await self._pool.fetch(
            "SELECT user_id FROM eventi_iscritti WHERE evento_id = $1 AND stato = $2 ORDER BY dal, user_id LIMIT $3 OFFSET $4",
            evento_id, stato, limite, scarto)
        return [r["user_id"] for r in righe]

    async def tutti_gli_iscritti(self, evento_id: int, limite: int, scarto: int = 0) -> list[tuple[int, str]]:
        """Tutti, per pagine: prima i «si», poi l'attesa, poi i «forse»."""
        righe = await self._pool.fetch(
            "SELECT user_id, stato FROM eventi_iscritti WHERE evento_id = $1 ORDER BY "
            "CASE stato WHEN 'si' THEN 0 WHEN 'attesa' THEN 1 ELSE 2 END, dal, user_id LIMIT $2 OFFSET $3",
            evento_id, limite, scarto)
        return [(r["user_id"], r["stato"]) for r in righe]

    # --- modifica e annullo -----------------------------------------------------------------------------------------
    async def modifica(self, evento_id: int, *, titolo: str | None = None, descrizione: str | None = None,
                       quando: datetime | None = None, posti: int | None = None, togli_posti: bool = False) -> list[int] | None:
        """Cambia i campi dati. Con più posti la lista d'attesa scorre; con meno, chi c'è resta. Torna i promossi,
        o None se l'evento non è più attivo."""
        async with self._pool.acquire() as conn, conn.transaction():
            await self._blocco(conn, evento_id)
            if await conn.fetchval("SELECT stato FROM eventi WHERE id = $1", evento_id) != "attivo":
                return None
            await conn.execute(
                "UPDATE eventi SET titolo = COALESCE($2, titolo), descrizione = COALESCE($3, descrizione), "
                "quando = COALESCE($4, quando), posti = CASE WHEN $6 THEN NULL ELSE COALESCE($5, posti) END WHERE id = $1",
                evento_id, titolo, descrizione, quando, posti, togli_posti)
            nuovi = await conn.fetchval("SELECT posti FROM eventi WHERE id = $1", evento_id)
            return await self._riequilibra(conn, evento_id, nuovi)

    async def annulla(self, evento_id: int) -> bool:
        """Una volta sola. Falso se era già annullato."""
        async with self._pool.acquire() as conn, conn.transaction():
            await self._blocco(conn, evento_id)
            r = await conn.execute("UPDATE eventi SET stato = 'annullato' WHERE id = $1 AND stato = 'attivo'", evento_id)
        return r != "UPDATE 0"


def _get_pool():
    from core.database import db

    return db.pool


eventi_repo = EventiRepository(pool_provider=_get_pool)
