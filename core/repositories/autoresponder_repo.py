"""
core/repositories/autoresponder_repo.py
=======================================
Risposte automatiche del server (NF-10). Tabella:
core/migrations/0083_autoresponder.sql.
Funzioni coperte: SPEC §14.7 (NF-10), catalogo #128 UTL-060, 062, 064, 065, 066, 067 (r2utl)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.repositories.tetto_server import tetto_per_server

from core.autoresponder_logic import MAX_RISPOSTE


@dataclass(frozen=True)
class Autoresponder:
    id: int
    guild_id: int
    trigger: str
    match_mode: str
    response: str
    channel_id: int | None
    role_id: int | None
    ping_ruoli: bool
    maiuscole: bool = False
    canali_esclusi: tuple = ()
    utenti_esclusi: tuple = ()
    ruoli_esclusi: tuple = ()


_COLONNE = ("id, guild_id, trigger, match_mode, response, channel_id, role_id, ping_ruoli, maiuscole, "
            "canali_esclusi, utenti_esclusi, ruoli_esclusi")
_MODIFICABILI = {"match_mode", "response", "channel_id", "role_id", "ping_ruoli", "maiuscole"}
ESCLUSI = {"ruolo": "ruoli_esclusi", "canale": "canali_esclusi", "utente": "utenti_esclusi"}


class AutoresponderRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def create(
        self,
        guild_id: int,
        trigger: str,
        *,
        match_mode: str,
        response: str,
        channel_id: int | None,
        role_id: int | None,
        ping_ruoli: bool,
        created_by: int,
        maiuscole: bool = False,
    ) -> tuple[str, int | None]:
        """("ok", id), ("esiste", None) o ("pieno", None). Tetto e scrittura nella stessa query."""
        async with tetto_per_server(self._pool, "autoresponders", guild_id) as conn:
            riga = await conn.fetchrow(
                """
                INSERT INTO autoresponders
                    (guild_id, trigger, match_mode, response, channel_id, role_id, ping_ruoli, created_by, maiuscole)
                SELECT $1, $2, $3, $4, $5, $6, $7, $8, $10
                WHERE (SELECT count(*) FROM autoresponders WHERE guild_id = $1) < $9
                ON CONFLICT (guild_id, lower(trigger)) DO NOTHING
                RETURNING id
                """,
                guild_id, trigger, match_mode, response, channel_id, role_id, ping_ruoli, created_by, MAX_RISPOSTE, maiuscole,
            )
            if riga is not None:
                return "ok", riga["id"]
            esiste = await conn.fetchval(
                "SELECT 1 FROM autoresponders WHERE guild_id = $1 AND lower(trigger) = lower($2)", guild_id, trigger
            )
            return ("esiste" if esiste else "pieno"), None

    async def list(self, guild_id: int) -> list[Autoresponder]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM autoresponders WHERE guild_id = $1 ORDER BY id", guild_id
        )
        return [Autoresponder(**dict(r)) for r in righe]

    async def get(self, guild_id: int, responder_id: int) -> Autoresponder | None:
        r = await self._pool.fetchrow(
            f"SELECT {_COLONNE} FROM autoresponders WHERE guild_id = $1 AND id = $2", guild_id, responder_id)
        return None if r is None else Autoresponder(**dict(r))

    async def modifica(self, guild_id: int, responder_id: int, **campi) -> bool:
        """Cambia solo i campi dati (nomi da un elenco fisso, valori sempre come parametri)."""
        if not campi or not set(campi) <= _MODIFICABILI:
            raise ValueError(f"Campi non modificabili: {sorted(set(campi) - _MODIFICABILI)}")
        impostazioni = ", ".join(f"{col} = ${i}" for i, col in enumerate(campi, start=3))
        esito = await self._pool.execute(
            f"UPDATE autoresponders SET {impostazioni} WHERE guild_id = $1 AND id = $2", guild_id, responder_id, *campi.values())
        return esito.endswith(" 1")

    async def cambia_esclusione(self, guild_id: int, responder_id: int, tipo: str, valore: int, aggiungi: bool,
                                massimo: int) -> list[int] | None:
        """Mette o toglie un ruolo, canale o utente dagli esclusi. Ritorna l'elenco nuovo (None: la risposta non c'è)."""
        colonna = ESCLUSI[tipo]
        if aggiungi:
            sql = (f"UPDATE autoresponders SET {colonna} = CASE WHEN $3 = ANY({colonna}) OR cardinality({colonna}) >= $4 "
                   f"THEN {colonna} ELSE array_append({colonna}, $3) END WHERE guild_id = $1 AND id = $2 RETURNING {colonna}")
        else:
            sql = (f"UPDATE autoresponders SET {colonna} = array_remove({colonna}, $3) "
                   f"WHERE guild_id = $1 AND id = $2 AND $4::int > 0 RETURNING {colonna}")
        riga = await self._pool.fetchrow(sql, guild_id, responder_id, valore, massimo)
        return None if riga is None else list(riga[colonna])

    async def delete(self, guild_id: int, responder_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM autoresponders WHERE guild_id = $1 AND id = $2", guild_id, responder_id
        )
        return esito.endswith(" 1")


    async def svuota(self, guild_id: int) -> int:
        """Cancella tutte le risposte del server. Ritorna quante erano."""
        return int((await self._pool.execute("DELETE FROM autoresponders WHERE guild_id = $1", guild_id)).split()[-1])

    async def conta(self, guild_id: int) -> int:
        return await self._pool.fetchval("SELECT count(*) FROM autoresponders WHERE guild_id = $1", guild_id)


def _get_pool():
    from core.database import db
    return db.pool


autoresponder_repo = AutoresponderRepository(pool_provider=_get_pool)
