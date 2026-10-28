"""
core/repositories/desktop_repo.py
=================================
Dati di iYokai Desktop (migrazione 0452, SPEC D.1, D.5-D.7, D.9): token (solo impronta), scelte di avviso,
eventi per l'utente e azioni dello staff. Ogni riga è dell'utente; cancellazione ed esportazione passano
dal registro dei dati.
Funzioni coperte: SPEC D.1, D.5-D.7, D.9 (#108)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.desktop_logic import MAX_EVENTI_PER_UTENTE


@dataclass(frozen=True)
class PreferenzeDesktop:
    menzioni: bool = False
    parole: tuple[str, ...] = ()


class DesktopRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- token
    async def imposta_token(self, user_id: int, impronta: str) -> None:
        """Un solo collegamento a persona: un token nuovo sostituisce il vecchio."""
        await self._pool.execute(
            """INSERT INTO desktop_tokens (user_id, token_hash) VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET token_hash = EXCLUDED.token_hash, created_at = now(), last_used_at = NULL""",
            user_id, impronta,
        )

    async def revoca_token(self, user_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM desktop_tokens WHERE user_id = $1", user_id)
        return esito.endswith(" 1")

    async def utente_del_token(self, impronta: str) -> int | None:
        return await self._pool.fetchval(
            "UPDATE desktop_tokens SET last_used_at = now() WHERE token_hash = $1 RETURNING user_id", impronta
        )

    async def collegato(self, user_id: int) -> bool:
        return bool(await self._pool.fetchval("SELECT 1 FROM desktop_tokens WHERE user_id = $1", user_id))

    # ---------------------------------------------------------------- avvisi
    async def preferenze(self, user_id: int) -> PreferenzeDesktop:
        riga = await self._pool.fetchrow("SELECT menzioni, parole FROM desktop_prefs WHERE user_id = $1", user_id)
        return PreferenzeDesktop() if riga is None else PreferenzeDesktop(riga["menzioni"], tuple(riga["parole"]))

    async def imposta_menzioni(self, user_id: int, acceso: bool) -> None:
        await self._pool.execute(
            """INSERT INTO desktop_prefs (user_id, menzioni) VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET menzioni = EXCLUDED.menzioni""",
            user_id, acceso,
        )

    async def imposta_parole(self, user_id: int, parole: list[str]) -> None:
        await self._pool.execute(
            """INSERT INTO desktop_prefs (user_id, parole) VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET parole = EXCLUDED.parole""",
            user_id, parole,
        )

    async def utenti_con_avvisi(self) -> dict[int, list[str]]:
        """Chi ha acceso gli avvisi, con le sue parole chiave: la lista che il bot guarda a ogni messaggio."""
        righe = await self._pool.fetch("SELECT user_id, parole FROM desktop_prefs WHERE menzioni")
        return {r["user_id"]: list(r["parole"]) for r in righe}

    # ---------------------------------------------------------------- eventi
    async def aggiungi_evento(
        self, user_id: int, tipo: str, *, guild_id: int | None = None, channel_id: int | None = None,
        message_id: int | None = None, autore_id: int | None = None, autore_nome: str | None = None,
        canale_nome: str | None = None, testo: str | None = None, massimo: int = MAX_EVENTI_PER_UTENTE,
    ) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """INSERT INTO desktop_eventi (user_id, tipo, guild_id, channel_id, message_id, autore_id,
                                               autore_nome, canale_nome, testo)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                user_id, tipo, guild_id, channel_id, message_id, autore_id, autore_nome, canale_nome, testo,
            )
            await conn.execute(
                """DELETE FROM desktop_eventi WHERE user_id = $1 AND id NOT IN
                   (SELECT id FROM desktop_eventi WHERE user_id = $1 ORDER BY id DESC LIMIT $2)""",
                user_id, massimo,
            )

    async def eventi(
        self, user_id: int, dopo: int = 0, tipo: str | None = None, limite: int = 50
    ) -> list[asyncpg.Record]:
        """Dal più vecchio al più nuovo, dopo l'id dato (il programma ricorda l'ultimo visto)."""
        return await self._pool.fetch(
            """SELECT * FROM (
                   SELECT * FROM desktop_eventi WHERE user_id = $1 AND id > $2 AND ($3::text IS NULL OR tipo = $3)
                   ORDER BY id DESC LIMIT $4) ultimi ORDER BY id""",
            user_id, dopo, tipo, limite,
        )

    # ---------------------------------------------------------------- azioni dello staff
    async def registra_azione(self, user_id: int, guild_id: int, azione: str, dettaglio: str, esito: str) -> None:
        await self._pool.execute(
            "INSERT INTO desktop_azioni (user_id, guild_id, azione, dettaglio, esito) VALUES ($1, $2, $3, $4, $5)",
            user_id, guild_id, azione, dettaglio[:300], esito,
        )

    async def azioni_server(self, guild_id: int, limite: int = 25) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT * FROM desktop_azioni WHERE guild_id = $1 ORDER BY id DESC LIMIT $2", guild_id, limite
        )

    async def azioni_utente(self, user_id: int, limite: int = 25) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT * FROM desktop_azioni WHERE user_id = $1 ORDER BY id DESC LIMIT $2", user_id, limite
        )


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


desktop_repo = DesktopRepository(pool_provider=_get_pool)
