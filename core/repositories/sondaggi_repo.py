"""
core/repositories/sondaggi_repo.py
==================================
Archivio dei sondaggi a bottoni: sondaggi, opzioni, voti (mentre è aperto) e pesi per ruolo. Ogni voto e la chiusura
girano sotto un blocco per sondaggio: due clic insieme non danno mai due voti né due chiusure.
Tabelle: core/migrations/0559_sondaggi_bottoni.sql.
Funzioni coperte: catalogo #128 UTL-088, 089, 091, 093, 094, 096, 090, 097 (D69, B22, B23)
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

from core.sondaggi_logic import MAX_PESI, scelte_dopo_voto

_COLONNE = (
    "id, guild_id, channel_id, message_id, autore_id, domanda, anonimo, risultati, multipla, pesato, ruoli, "
    "chiudi_a_voti, inizia_il, scade_il, durata_s, stato, chiuso_il"
)


class SondaggiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def crea(
        self, guild_id: int, channel_id: int, autore_id: int, domanda: str, opzioni: list[str], *, anonimo: bool = False,
        risultati: str = "subito", multipla: bool = False, pesato: bool = False, ruoli: list[int] | None = None,
        chiudi_a_voti: int | None = None, inizia_il: datetime | None = None, scade_il: datetime | None = None,
        durata_s: int | None = None, stato: str = "aperto",
    ) -> int:
        async with self._pool.acquire() as conn, conn.transaction():
            sid = await conn.fetchval(
                "INSERT INTO sondaggi (guild_id, channel_id, autore_id, domanda, anonimo, risultati, multipla, pesato, ruoli, "
                "chiudi_a_voti, inizia_il, scade_il, durata_s, stato) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) RETURNING id",
                guild_id, channel_id, autore_id, domanda, anonimo, risultati, multipla, pesato, ruoli or [],
                chiudi_a_voti, inizia_il, scade_il, durata_s, stato,
            )
            await conn.executemany(
                "INSERT INTO sondaggi_opzioni (sondaggio_id, n, testo) VALUES ($1, $2, $3)",
                [(sid, n, testo) for n, testo in enumerate(opzioni)],
            )
        return sid

    async def prendi(self, sondaggio_id: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow(f"SELECT {_COLONNE} FROM sondaggi WHERE id = $1", sondaggio_id)

    async def imposta_messaggio(self, sondaggio_id: int, message_id: int) -> None:
        await self._pool.execute("UPDATE sondaggi SET message_id = $2 WHERE id = $1", sondaggio_id, message_id)

    async def opzioni(self, sondaggio_id: int) -> list[str]:
        righe = await self._pool.fetch("SELECT testo FROM sondaggi_opzioni WHERE sondaggio_id = $1 ORDER BY n", sondaggio_id)
        return [r["testo"] for r in righe]

    async def risultati(self, sondaggio_id: int, pesato: bool) -> list[tuple[str, int]]:
        """(testo, totale) per opzione: i voti vivi se il sondaggio è aperto, i totali salvati se è chiuso."""
        righe = await self._pool.fetch(
            "SELECT o.testo, CASE WHEN s.stato = 'chiuso' THEN CASE WHEN $2 THEN o.voti_pesati ELSE o.voti END "
            "ELSE COALESCE((SELECT CASE WHEN $2 THEN sum(v.peso) ELSE count(*) END FROM sondaggi_voti v "
            "WHERE v.sondaggio_id = o.sondaggio_id AND v.n = o.n), 0) END AS totale "
            "FROM sondaggi_opzioni o JOIN sondaggi s ON s.id = o.sondaggio_id WHERE o.sondaggio_id = $1 ORDER BY o.n",
            sondaggio_id, pesato,
        )
        return [(r["testo"], int(r["totale"])) for r in righe]

    async def apri(self, sondaggio_id: int, scade_il: datetime) -> bool:
        """Da «programmato» ad «aperto», una volta sola, con la scadenza calcolata ora. Falso se non spetta più."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('sondaggio'), $1)", sondaggio_id % 2**31)
            r = await conn.execute(
                "UPDATE sondaggi SET stato = 'aperto', scade_il = $2 WHERE id = $1 AND stato = 'programmato'", sondaggio_id, scade_il)
        return r != "UPDATE 0"

    async def elenco_gestione(self, guild_id: int, autore_id: int | None = None, *, anche_chiusi: bool = False,
                              limite: int = 25) -> list[asyncpg.Record]:
        """Sondaggi programmati e aperti (anche i chiusi, a richiesta), i più nuovi prima."""
        return await self._pool.fetch(
            f"SELECT {_COLONNE} FROM sondaggi WHERE guild_id = $1 AND ($2::bigint IS NULL OR autore_id = $2) "
            "AND ($3 OR stato <> 'chiuso') ORDER BY id DESC LIMIT $4", guild_id, autore_id, anche_chiusi, limite)

    async def votanti(self, sondaggio_id: int) -> int:
        return await self._pool.fetchval("SELECT count(DISTINCT user_id) FROM sondaggi_voti WHERE sondaggio_id = $1", sondaggio_id)

    async def vota(self, sondaggio_id: int, user_id: int, scelta: int, peso: int, adesso: datetime) -> tuple[str, set[int], int]:
        """(esito, scelte del votante, votanti). Esiti: «ok», «uguale» (stessa scelta di prima), «chiuso», «senza_opzione»."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('sondaggio'), $1)", sondaggio_id % 2**31)
            s = await conn.fetchrow("SELECT guild_id, multipla, stato, scade_il FROM sondaggi WHERE id = $1", sondaggio_id)
            if s is None or s["stato"] != "aperto" or (s["scade_il"] and s["scade_il"] <= adesso):
                return "chiuso", set(), 0
            if not await conn.fetchval("SELECT 1 FROM sondaggi_opzioni WHERE sondaggio_id = $1 AND n = $2", sondaggio_id, scelta):
                return "senza_opzione", set(), 0
            attuali = {r["n"] for r in await conn.fetch(
                "SELECT n FROM sondaggi_voti WHERE sondaggio_id = $1 AND user_id = $2", sondaggio_id, user_id)}
            nuove = scelte_dopo_voto(attuali, scelta, s["multipla"])
            if nuove == attuali:
                return "uguale", attuali, 0
            await conn.execute("DELETE FROM sondaggi_voti WHERE sondaggio_id = $1 AND user_id = $2", sondaggio_id, user_id)
            if nuove:
                await conn.executemany(
                    "INSERT INTO sondaggi_voti (guild_id, sondaggio_id, user_id, n, peso) VALUES ($1, $2, $3, $4, $5)",
                    [(s["guild_id"], sondaggio_id, user_id, n, peso) for n in sorted(nuove)],
                )
            votanti = await conn.fetchval("SELECT count(DISTINCT user_id) FROM sondaggi_voti WHERE sondaggio_id = $1", sondaggio_id)
        return "ok", nuove, votanti

    async def togli_voto(self, sondaggio_id: int, user_id: int) -> bool:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('sondaggio'), $1)", sondaggio_id % 2**31)
            if await conn.fetchval("SELECT stato FROM sondaggi WHERE id = $1", sondaggio_id) != "aperto":
                return False
            r = await conn.execute("DELETE FROM sondaggi_voti WHERE sondaggio_id = $1 AND user_id = $2", sondaggio_id, user_id)
        return r != "DELETE 0"

    async def togli_voti_utente(self, guild_id: int, user_id: int) -> int:
        """Chi esce o è bannato perde i voti dei sondaggi ancora aperti (UTL-096)."""
        r = await self._pool.execute(
            "DELETE FROM sondaggi_voti v USING sondaggi s WHERE v.sondaggio_id = s.id AND s.stato = 'aperto' "
            "AND v.guild_id = $1 AND v.user_id = $2", guild_id, user_id,
        )
        return int(r.split()[-1])

    async def chiudi(self, sondaggio_id: int) -> bool:
        """Chiude una volta sola: salva i totali e svuota i voti (anche degli anonimi). Falso se era già chiuso."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('sondaggio'), $1)", sondaggio_id % 2**31)
            if await conn.fetchval("SELECT stato FROM sondaggi WHERE id = $1", sondaggio_id) not in ("aperto", "programmato"):
                return False
            await conn.execute(
                "UPDATE sondaggi_opzioni o SET "
                "voti = (SELECT count(*) FROM sondaggi_voti v WHERE v.sondaggio_id = o.sondaggio_id AND v.n = o.n), "
                "voti_pesati = COALESCE((SELECT sum(v.peso) FROM sondaggi_voti v WHERE v.sondaggio_id = o.sondaggio_id AND v.n = o.n), 0) "
                "WHERE o.sondaggio_id = $1", sondaggio_id,
            )
            await conn.execute("DELETE FROM sondaggi_voti WHERE sondaggio_id = $1", sondaggio_id)
            await conn.execute("UPDATE sondaggi SET stato = 'chiuso', chiuso_il = now() WHERE id = $1", sondaggio_id)
        return True

    async def votanti_per_opzione(self, sondaggio_id: int) -> dict[int, list[int]]:
        righe = await self._pool.fetch("SELECT n, user_id FROM sondaggi_voti WHERE sondaggio_id = $1 ORDER BY n, user_id", sondaggio_id)
        fuori: dict[int, list[int]] = {}
        for r in righe:
            fuori.setdefault(r["n"], []).append(r["user_id"])
        return fuori

    async def elimina(self, sondaggio_id: int) -> None:
        await self._pool.execute("DELETE FROM sondaggi WHERE id = $1", sondaggio_id)

    async def elimina_del_canale(self, guild_id: int, channel_id: int) -> int:
        """Toglie i sondaggi di un canale cancellato. Torna quanti."""
        r = await self._pool.execute("DELETE FROM sondaggi WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id)
        return int(r.split()[-1])

    async def modifica(self, sondaggio_id: int, domanda: str, opzioni: list[str], scade_il: datetime | None) -> int | None:
        """Cambia domanda, opzioni e scadenza di un sondaggio aperto. Le opzioni con lo stesso testo tengono i voti, le
        tolte li perdono. Torna quanti voti sono stati persi, o None se il sondaggio non è più aperto."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('sondaggio'), $1)", sondaggio_id % 2**31)
            if await conn.fetchval("SELECT stato FROM sondaggi WHERE id = $1", sondaggio_id) != "aperto":
                return None
            vecchie = await conn.fetch("SELECT n, testo FROM sondaggi_opzioni WHERE sondaggio_id = $1", sondaggio_id)
            nuove = {t.casefold(): n for n, t in enumerate(opzioni)}
            mappa = [(v["n"], nuove[v["testo"].casefold()]) for v in vecchie if v["testo"].casefold() in nuove]
            await conn.execute("UPDATE sondaggi_voti SET n = n + 1000 WHERE sondaggio_id = $1", sondaggio_id)
            for vecchio, nuovo in mappa:
                await conn.execute("UPDATE sondaggi_voti SET n = $3 WHERE sondaggio_id = $1 AND n = $2", sondaggio_id, vecchio + 1000, nuovo)
            persi = await conn.execute("DELETE FROM sondaggi_voti WHERE sondaggio_id = $1 AND n >= 1000", sondaggio_id)
            await conn.execute("DELETE FROM sondaggi_opzioni WHERE sondaggio_id = $1", sondaggio_id)
            await conn.executemany(
                "INSERT INTO sondaggi_opzioni (sondaggio_id, n, testo) VALUES ($1, $2, $3)",
                [(sondaggio_id, n, testo) for n, testo in enumerate(opzioni)],
            )
            await conn.execute("UPDATE sondaggi SET domanda = $2, scade_il = COALESCE($3, scade_il) WHERE id = $1", sondaggio_id, domanda, scade_il)
        return int(persi.split()[-1])

    async def imposta_ruoli(self, sondaggio_id: int, ruoli: list[int]) -> None:
        await self._pool.execute("UPDATE sondaggi SET ruoli = $2 WHERE id = $1", sondaggio_id, ruoli)

    async def elenco(self, guild_id: int, autore_id: int | None = None, stato: str | None = None, limite: int = 25) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            f"SELECT {_COLONNE} FROM sondaggi WHERE guild_id = $1 AND ($2::bigint IS NULL OR autore_id = $2) "
            "AND ($3::text IS NULL OR stato = $3) ORDER BY id DESC LIMIT $4",
            guild_id, autore_id, stato, limite,
        )

    async def cerca_domanda(self, guild_id: int, testo: str, autore_id: int | None, limite: int = 25) -> list[asyncpg.Record]:
        pulito = testo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return await self._pool.fetch(
            "SELECT id, domanda, stato FROM sondaggi WHERE guild_id = $1 AND ($2::bigint IS NULL OR autore_id = $2) "
            "AND domanda ILIKE $3 ORDER BY id DESC LIMIT $4", guild_id, autore_id, f"%{pulito}%", limite,
        )

    # --- pesi per ruolo -------------------------------------------------------------------------------------------
    async def pesi(self, guild_id: int) -> dict[int, int]:
        righe = await self._pool.fetch("SELECT ruolo_id, peso FROM sondaggi_pesi WHERE guild_id = $1", guild_id)
        return {r["ruolo_id"]: r["peso"] for r in righe}

    async def imposta_peso(self, guild_id: int, ruolo_id: int, peso: int) -> str:
        """«ok» oppure «pieno» (25 ruoli con peso per server)."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('sondaggi_pesi'), $1)", guild_id % 2**31)
            esiste = await conn.fetchval("SELECT 1 FROM sondaggi_pesi WHERE guild_id = $1 AND ruolo_id = $2", guild_id, ruolo_id)
            if not esiste and await conn.fetchval("SELECT count(*) FROM sondaggi_pesi WHERE guild_id = $1", guild_id) >= MAX_PESI:
                return "pieno"
            await conn.execute(
                "INSERT INTO sondaggi_pesi (guild_id, ruolo_id, peso) VALUES ($1, $2, $3) "
                "ON CONFLICT (guild_id, ruolo_id) DO UPDATE SET peso = EXCLUDED.peso", guild_id, ruolo_id, peso,
            )
        return "ok"

    async def togli_peso(self, guild_id: int, ruolo_id: int) -> bool:
        r = await self._pool.execute("DELETE FROM sondaggi_pesi WHERE guild_id = $1 AND ruolo_id = $2", guild_id, ruolo_id)
        return r != "DELETE 0"


def _get_pool():
    from core.database import db

    return db.pool


sondaggi_repo = SondaggiRepository(pool_provider=_get_pool)
