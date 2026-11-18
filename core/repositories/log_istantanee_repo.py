"""
core/repositories/log_istantanee_repo.py
========================================
Le istantanee di un canale (LOG-028): intestazione e righe. Si trovano solo con l'impronta del segreto del link.
Il tetto per server si controlla dentro la transazione, con un blocco per server: due richieste insieme non lo superano.
Funzioni coperte: SPEC §8.21 (LOG-028)
Dipende da: core/migrations/0711_log_istantanee.sql
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class Istantanea:
    id: int
    guild_id: int
    channel_id: int
    nome_canale: str
    creata_da: int
    creata_il: datetime
    scade_il: datetime
    accesso: str
    role_id: int | None


_COLONNE = "id, guild_id, channel_id, nome_canale, creata_da, creata_il, scade_il, accesso, role_id"


def _istantanea(r) -> Istantanea:
    return Istantanea(**{k: r[k] for k in Istantanea.__dataclass_fields__})


class LogIstantaneeRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def crea(
        self, guild_id: int, channel_id: int, nome_canale: str, creata_da: int, giorni: int, accesso: str,
        role_id: int | None, impronta: str, righe: list[dict], massimo_attive: int,
    ) -> int | None:
        """L'id della nuova istantanea, o None se il server ne ha già `massimo_attive` ancora valide."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                attive = await conn.fetchval(
                    "SELECT count(*) FROM log_istantanee WHERE guild_id=$1 AND scade_il > now()", guild_id
                )
                if attive >= massimo_attive:
                    return None
                nuova = await conn.fetchval(
                    "INSERT INTO log_istantanee (guild_id, channel_id, nome_canale, creata_da, scade_il, accesso, "
                    "role_id, impronta) VALUES ($1, $2, $3, $4, now() + make_interval(days => $5), $6, $7, $8) "
                    "RETURNING id",
                    guild_id, channel_id, nome_canale, creata_da, giorni, accesso, role_id, impronta,
                )
                await conn.executemany(
                    "INSERT INTO log_istantanee_righe (istantanea_id, posizione, guild_id, message_id, author_id, "
                    "autore_nome, quando, testo, cancellato) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                    [
                        (nuova, i, guild_id, r["message_id"], r["author_id"], r["autore_nome"], r["quando"], r["testo"],
                         r["cancellato"])
                        for i, r in enumerate(righe)
                    ],
                )
                return nuova

    async def elenco(self, guild_id: int, limite: int = 25) -> list[Istantanea]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM log_istantanee WHERE guild_id=$1 AND scade_il > now() ORDER BY id DESC LIMIT $2",
            guild_id, limite,
        )
        return [_istantanea(r) for r in righe]

    async def revoca(self, guild_id: int, istantanea_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM log_istantanee WHERE guild_id=$1 AND id=$2", guild_id, istantanea_id
        )
        return esito.endswith(" 1")

    async def per_impronta(self, impronta: str) -> Istantanea | None:
        """Solo se non è scaduta."""
        riga = await self._pool.fetchrow(
            f"SELECT {_COLONNE} FROM log_istantanee WHERE impronta=$1 AND scade_il > now()", impronta
        )
        return _istantanea(riga) if riga else None

    async def righe(self, istantanea_id: int) -> list[dict]:
        righe = await self._pool.fetch(
            "SELECT message_id, author_id, autore_nome, quando, testo, cancellato FROM log_istantanee_righe "
            "WHERE istantanea_id=$1 ORDER BY posizione",
            istantanea_id,
        )
        return [dict(r) for r in righe]

    async def pulisci_scadute(self) -> int:
        esito = await self._pool.execute("DELETE FROM log_istantanee WHERE scade_il <= now()")
        return int(esito.split()[-1])


def _get_pool():
    from core.database import db
    return db.pool


log_istantanee_repo = LogIstantaneeRepository(pool_provider=_get_pool)
