"""
core/repositories/user_app_repo.py
==================================
Dati personali di iYokai App (migrazione 0451, SPEC B.2, B.5, B.8, B.9, B.10): segnalibri, risposte salvate,
impostazioni, storico dei comandi, playlist, richieste di assistenza, e le somme per il profilo globale.
Ogni riga è dell'utente; cancellazione ed esportazione passano dal registro dei dati.
Funzioni coperte: SPEC §B (NF-36, #107)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

MAX_SEGNALIBRI = 100
MAX_RISPOSTE = 50
MAX_STORICO = 100
MAX_PLAYLIST = 10
MAX_BRANI = 50
MAX_RICHIESTE_APERTE = 3


@dataclass(frozen=True)
class Impostazioni:
    risposte_private: bool = True
    dm_ok: bool = True
    storico: bool = False
    profilo_pubblico: bool = False


CAMPI_IMPOSTAZIONI = ("risposte_private", "dm_ok", "storico", "profilo_pubblico")


@dataclass(frozen=True)
class SommeGlobali:
    xp_totale: int
    server: int
    monete: int


class UserAppRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- segnalibri (B.2)
    async def salva_segnalibro(
        self, user_id: int, guild_id: int | None, channel_id: int, message_id: int, autore: str, testo: str,
        massimo: int = MAX_SEGNALIBRI,
    ) -> int | None:
        """Il numero del segnalibro; già salvato = lo stesso numero; None se l'utente è al tetto."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            esistente = await conn.fetchval(
                "SELECT id FROM user_app_bookmarks WHERE user_id = $1 AND message_id = $2", user_id, message_id
            )
            if esistente is not None:
                return esistente
            if await conn.fetchval("SELECT count(*) FROM user_app_bookmarks WHERE user_id = $1", user_id) >= massimo:
                return None
            return await conn.fetchval(
                "INSERT INTO user_app_bookmarks (user_id, guild_id, channel_id, message_id, autore, testo) "
                "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                user_id, guild_id, channel_id, message_id, autore, testo,
            )

    async def segnalibri(self, user_id: int, limite: int = 25, dopo: int = 0) -> list[asyncpg.Record]:
        """I segnalibri più recenti prima; `dopo` = numero dell'ultimo già visto (pagina successiva)."""
        return await self._pool.fetch(
            "SELECT id, guild_id, channel_id, message_id, autore, testo, created_at FROM user_app_bookmarks "
            "WHERE user_id = $1 AND ($3 = 0 OR id < $3) ORDER BY id DESC LIMIT $2",
            user_id, limite, dopo,
        )

    async def rimuovi_segnalibro(self, user_id: int, numero: int) -> bool:
        esito = await self._pool.execute("DELETE FROM user_app_bookmarks WHERE id = $1 AND user_id = $2", numero, user_id)
        return esito.endswith(" 1")

    # ---------------------------------------------------------------- risposte salvate (B.5)
    async def salva_risposta(
        self, user_id: int, nome: str, testo: str, titolo: str | None = None, colore: int | None = None,
        immagine_url: str | None = None, massimo: int = MAX_RISPOSTE,
    ) -> str:
        """'nuova', 'aggiornata' o 'piena' (tetto raggiunto, nome nuovo)."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            esiste = await conn.fetchval("SELECT 1 FROM user_app_replies WHERE user_id = $1 AND nome = $2", user_id, nome)
            if not esiste and await conn.fetchval("SELECT count(*) FROM user_app_replies WHERE user_id = $1", user_id) >= massimo:
                return "piena"
            await conn.execute(
                "INSERT INTO user_app_replies (user_id, nome, testo, titolo, colore, immagine_url) "
                "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (user_id, nome) DO UPDATE SET "
                "testo = EXCLUDED.testo, titolo = EXCLUDED.titolo, colore = EXCLUDED.colore, "
                "immagine_url = EXCLUDED.immagine_url",
                user_id, nome, testo, titolo, colore, immagine_url,
            )
            return "aggiornata" if esiste else "nuova"

    async def risposta(self, user_id: int, nome: str) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            "SELECT nome, testo, titolo, colore, immagine_url FROM user_app_replies WHERE user_id = $1 AND nome = $2",
            user_id, nome,
        )

    async def nomi_risposte(self, user_id: int, inizio: str = "", limite: int = 25) -> list[str]:
        righe = await self._pool.fetch(
            "SELECT nome FROM user_app_replies WHERE user_id = $1 AND nome LIKE $2 ORDER BY nome LIMIT $3",
            user_id, inizio.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", limite,
        )
        return [r["nome"] for r in righe]

    async def rimuovi_risposta(self, user_id: int, nome: str) -> bool:
        esito = await self._pool.execute("DELETE FROM user_app_replies WHERE user_id = $1 AND nome = $2", user_id, nome)
        return esito.endswith(" 1")

    # ---------------------------------------------------------------- impostazioni (B.10)
    async def impostazioni(self, user_id: int) -> Impostazioni:
        riga = await self._pool.fetchrow(
            "SELECT risposte_private, dm_ok, storico, profilo_pubblico FROM user_app_settings WHERE user_id = $1", user_id
        )
        return Impostazioni(**dict(riga)) if riga else Impostazioni()

    async def imposta(self, user_id: int, campo: str, valore: bool) -> None:
        if campo not in CAMPI_IMPOSTAZIONI:
            raise ValueError(f"Impostazione sconosciuta: {campo}")
        # Il nome della colonna viene dall'elenco fisso qui sopra, mai dall'utente.
        await self._pool.execute(
            f"INSERT INTO user_app_settings (user_id, {campo}) VALUES ($1, $2) "
            f"ON CONFLICT (user_id) DO UPDATE SET {campo} = EXCLUDED.{campo}, updated_at = now()",
            user_id, valore,
        )
        if campo == "storico" and not valore:
            await self.azzera_storico(user_id)

    # ---------------------------------------------------------------- storico (B.10, D.7)
    async def registra_comando(self, user_id: int, comando: str, guild_id: int | None, massimo: int = MAX_STORICO) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO user_app_history (user_id, comando, guild_id) VALUES ($1, $2, $3)", user_id, comando[:100], guild_id
            )
            await conn.execute(
                "DELETE FROM user_app_history WHERE user_id = $1 AND id NOT IN "
                "(SELECT id FROM user_app_history WHERE user_id = $1 ORDER BY id DESC LIMIT $2)",
                user_id, massimo,
            )

    async def storico(self, user_id: int, limite: int = 25) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT comando, guild_id, used_at FROM user_app_history WHERE user_id = $1 ORDER BY id DESC LIMIT $2",
            user_id, limite,
        )

    async def azzera_storico(self, user_id: int) -> int:
        esito = await self._pool.execute("DELETE FROM user_app_history WHERE user_id = $1", user_id)
        return int(esito.rsplit(" ", 1)[-1])

    # ---------------------------------------------------------------- playlist (B.8)
    async def crea_playlist(self, user_id: int, nome: str, massimo: int = MAX_PLAYLIST) -> bool:
        """False se esiste già o l'utente è al tetto."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            if await conn.fetchval("SELECT count(*) FROM user_app_playlists WHERE user_id = $1", user_id) >= massimo:
                return False
            esito = await conn.execute(
                "INSERT INTO user_app_playlists (user_id, nome) VALUES ($1, $2) ON CONFLICT DO NOTHING", user_id, nome
            )
            return esito.endswith(" 1")

    async def aggiungi_brano(self, user_id: int, nome: str, brano: str, massimo: int = MAX_BRANI) -> str:
        """'ok', 'manca' (playlist inesistente) o 'piena'."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            brani = await conn.fetchval("SELECT brani FROM user_app_playlists WHERE user_id = $1 AND nome = $2", user_id, nome)
            if brani is None:
                return "manca"
            if len(brani) >= massimo:
                return "piena"
            await conn.execute(
                "UPDATE user_app_playlists SET brani = array_append(brani, $3) WHERE user_id = $1 AND nome = $2",
                user_id, nome, brano,
            )
            return "ok"

    async def togli_brano(self, user_id: int, nome: str, posizione: int) -> bool:
        """Toglie il brano alla posizione (da 1)."""
        async with self._pool.acquire() as conn, conn.transaction():
            brani = await conn.fetchval(
                "SELECT brani FROM user_app_playlists WHERE user_id = $1 AND nome = $2 FOR UPDATE", user_id, nome
            )
            if brani is None or not 1 <= posizione <= len(brani):
                return False
            del brani[posizione - 1]
            await conn.execute("UPDATE user_app_playlists SET brani = $3 WHERE user_id = $1 AND nome = $2", user_id, nome, brani)
            return True

    async def playlist(self, user_id: int, nome: str) -> list[str] | None:
        return await self._pool.fetchval("SELECT brani FROM user_app_playlists WHERE user_id = $1 AND nome = $2", user_id, nome)

    async def elenco_playlist(self, user_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT nome, cardinality(brani) AS brani FROM user_app_playlists WHERE user_id = $1 ORDER BY nome", user_id
        )

    async def rimuovi_playlist(self, user_id: int, nome: str) -> bool:
        esito = await self._pool.execute("DELETE FROM user_app_playlists WHERE user_id = $1 AND nome = $2", user_id, nome)
        return esito.endswith(" 1")

    # ---------------------------------------------------------------- assistenza (B.9)
    async def apri_richiesta(
        self, user_id: int, oggetto: str, testo: str, massimo_aperte: int = MAX_RICHIESTE_APERTE
    ) -> int | None:
        """Il numero della richiesta, o None se l'utente ne ha già `massimo_aperte` aperte."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            aperte = await conn.fetchval(
                "SELECT count(*) FROM support_requests WHERE user_id = $1 AND stato = 'aperta'", user_id
            )
            if aperte >= massimo_aperte:
                return None
            return await conn.fetchval(
                "INSERT INTO support_requests (user_id, oggetto, testo) VALUES ($1, $2, $3) RETURNING id",
                user_id, oggetto, testo,
            )

    async def imposta_thread_richiesta(self, numero: int, thread_id: int) -> None:
        await self._pool.execute("UPDATE support_requests SET thread_id = $2 WHERE id = $1", numero, thread_id)

    async def richiesta(self, numero: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            "SELECT id, user_id, oggetto, stato, thread_id FROM support_requests WHERE id = $1", numero
        )

    async def richiesta_da_thread(self, thread_id: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            "SELECT id, user_id, oggetto, stato FROM support_requests WHERE thread_id = $1", thread_id
        )

    async def chiudi_richiesta(self, numero: int) -> None:
        await self._pool.execute(
            "UPDATE support_requests SET stato = 'chiusa', closed_at = now() WHERE id = $1 AND stato = 'aperta'", numero
        )

    async def richieste_utente(self, user_id: int, limite: int = 10) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT id, oggetto, stato, created_at FROM support_requests WHERE user_id = $1 ORDER BY id DESC LIMIT $2",
            user_id, limite,
        )

    # ---------------------------------------------------------------- profilo globale (B.6)
    async def somme_globali(self, user_id: int) -> SommeGlobali:
        riga = await self._pool.fetchrow(
            "SELECT COALESCE(sum(xp_total), 0) AS xp, count(*) FILTER (WHERE xp_total > 0) AS server, "
            "COALESCE(sum(coins_total), 0) AS monete FROM leveling_totals WHERE user_id = $1",
            user_id,
        )
        return SommeGlobali(int(riga["xp"]), int(riga["server"]), int(riga["monete"]))

    async def clan_dell_utente(self, user_id: int, limite: int = 10) -> list[asyncpg.Record]:
        """I clan a cui appartiene, uno per server: nome e tag."""
        return await self._pool.fetch(
            "SELECT c.name, c.tag, c.guild_id FROM clans c JOIN clan_members m ON m.clan_id = c.id "
            "WHERE m.user_id = $1 ORDER BY c.name LIMIT $2",
            user_id, limite,
        )

    async def medaglie(self, user_id: int) -> list[str]:
        """Gli id degli oggetti posseduti in qualsiasi server, senza doppioni."""
        righe = await self._pool.fetch(
            "SELECT DISTINCT item_id FROM profile_items WHERE user_id = $1 ORDER BY item_id", user_id
        )
        return [r["item_id"] for r in righe]


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


user_app_repo = UserAppRepository(pool_provider=_get_pool)
