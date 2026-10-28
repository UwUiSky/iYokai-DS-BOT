"""
core/repositories/odio_libreria_repo.py
=======================================
Libreria mondiale delle parole d'odio e delle loro varianti (D35).
Tabelle: core/migrations/0390_odio_libreria.sql, 0391 (proprietario del server).
Funzioni coperte: SPEC §6 (D35)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.odio_libreria_logic import (
    MAX_CANDIDATE_PER_SERVER,
    STATI_GLOBALI,
    STATO_BASE,
    STATO_CANDIDATA,
    STATO_CONDIVISA,
    STATO_RIFIUTATA,
    stato_dopo_segnalazione,
)


@dataclass(frozen=True)
class ParolaOdio:
    id: int
    variante: str
    lingua: str
    stato: str
    server: int = 0  # in segnala(): proprietari diversi; in elenca(): server che l'hanno segnalata


def _parola(r) -> ParolaOdio:
    return ParolaOdio(r["id"], r["variante"], r["lingua"], r["stato"], r["server"])


class OdioLibreriaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def segnala(self, variante: str, lingua: str, guild_id: int, owner_id: int | None) -> ParolaOdio | None:
        """
        Un server segnala una variante trovata dall'AI. Nuova: entra come candidata. Con
        segnalazioni da server di abbastanza proprietari diversi diventa condivisa (owner_id
        None = il server non conta per la soglia). Una rifiutata resta rifiutata. None se il
        server ha già troppe candidate.
        """
        async with self._pool.acquire() as conn, conn.transaction():
            riga = await conn.fetchrow("SELECT id, variante, lingua, stato FROM odio_parole WHERE variante = $1 FOR UPDATE", variante)
            if riga is None:
                if await self._candidate_del_server(conn, guild_id) >= MAX_CANDIDATE_PER_SERVER:
                    return None
                riga = await conn.fetchrow(
                    "INSERT INTO odio_parole (variante, lingua, stato) VALUES ($1, $2, $3) "
                    "ON CONFLICT (variante) DO UPDATE SET variante = EXCLUDED.variante "
                    "RETURNING id, variante, lingua, stato",
                    variante, lingua, STATO_CANDIDATA,
                )
            if riga["stato"] == STATO_RIFIUTATA:
                return ParolaOdio(riga["id"], riga["variante"], riga["lingua"], riga["stato"])
            await conn.execute(
                "INSERT INTO odio_segnalazioni (parola_id, guild_id, owner_id) VALUES ($1, $2, $3) "
                "ON CONFLICT (parola_id, guild_id) DO UPDATE SET owner_id = EXCLUDED.owner_id",
                riga["id"], guild_id, owner_id,
            )
            server = await conn.fetchval(
                "SELECT count(DISTINCT owner_id) FROM odio_segnalazioni WHERE parola_id = $1", riga["id"]
            )
            stato = stato_dopo_segnalazione(riga["stato"], server)
            if stato != riga["stato"]:
                await conn.execute("UPDATE odio_parole SET stato = $2, aggiornata_il = now() WHERE id = $1", riga["id"], stato)
            elif not riga["lingua"] and lingua:
                await conn.execute("UPDATE odio_parole SET lingua = $2 WHERE id = $1", riga["id"], lingua)
            return ParolaOdio(riga["id"], riga["variante"], riga["lingua"] or lingua, stato, server)

    @staticmethod
    async def _candidate_del_server(conn, guild_id: int) -> int:
        return await conn.fetchval(
            "SELECT count(*) FROM odio_segnalazioni s JOIN odio_parole p ON p.id = s.parola_id "
            "WHERE s.guild_id = $1 AND p.stato = $2",
            guild_id, STATO_CANDIDATA,
        )

    async def globali(self) -> tuple[str, ...]:
        """Le varianti che valgono in tutti i server (base e approvate)."""
        righe = await self._pool.fetch("SELECT variante FROM odio_parole WHERE stato = ANY($1::text[]) ORDER BY id", list(STATI_GLOBALI))
        return tuple(r["variante"] for r in righe)

    async def candidate_del_server(self, guild_id: int) -> tuple[str, ...]:
        """
        Le varianti sospette per questo server, da far giudicare all'AI: le sue candidate
        (valgono solo lì) più le condivise da abbastanza proprietari (valgono ovunque, D39).
        """
        righe = await self._pool.fetch(
            "SELECT variante FROM ("
            " SELECT p.id, p.variante FROM odio_parole p JOIN odio_segnalazioni s ON s.parola_id = p.id"
            " WHERE s.guild_id = $1 AND p.stato = $2"
            " UNION SELECT p.id, p.variante FROM odio_parole p WHERE p.stato = $4"
            ") v ORDER BY id LIMIT $3",
            guild_id, STATO_CANDIDATA, MAX_CANDIDATE_PER_SERVER + 500, STATO_CONDIVISA,
        )
        return tuple(r["variante"] for r in righe)

    async def elenca(self, stato: str, limite: int = 25) -> list[ParolaOdio]:
        righe = await self._pool.fetch(
            "SELECT p.id, p.variante, p.lingua, p.stato, count(s.guild_id) AS server "
            "FROM odio_parole p LEFT JOIN odio_segnalazioni s ON s.parola_id = p.id "
            "WHERE p.stato = $1 GROUP BY p.id ORDER BY count(s.guild_id) DESC, p.id LIMIT $2",
            stato, limite,
        )
        return [_parola(r) for r in righe]

    async def conta_per_stato(self) -> dict[str, int]:
        righe = await self._pool.fetch("SELECT stato, count(*) AS n FROM odio_parole GROUP BY stato")
        return {r["stato"]: r["n"] for r in righe}

    async def imposta_stato(self, variante: str, stato: str) -> bool:
        """Approva o rifiuta (decisione del proprietario). False se la variante non esiste."""
        esito = await self._pool.execute(
            "UPDATE odio_parole SET stato = $2, aggiornata_il = now() WHERE variante = $1", variante, stato
        )
        return esito.endswith(" 1")

    async def aggiungi_base(self, variante: str, lingua: str) -> None:
        """Il proprietario aggiunge direttamente una voce: vale subito in tutti i server."""
        await self._pool.execute(
            "INSERT INTO odio_parole (variante, lingua, stato) VALUES ($1, $2, $3) "
            "ON CONFLICT (variante) DO UPDATE SET stato = EXCLUDED.stato, aggiornata_il = now()",
            variante, lingua, STATO_BASE,
        )


def _get_pool():
    from core.database import db
    return db.pool


odio_libreria_repo = OdioLibreriaRepository(pool_provider=_get_pool)
