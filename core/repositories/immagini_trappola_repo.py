"""
core/repositories/immagini_trappola_repo.py
===========================================
Libreria mondiale delle immagini trappola (D62).
Tabelle: core/migrations/0505_immagini_trappola.sql, 0506_immagini_trappola_segnalazioni.sql.
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

import asyncpg

from core import immagini_trappola_logic as lg
from core.immagini_trappola_logic import Voce

_COLONNE = "encode(t.sha256, 'hex') AS sha256, t.dhash, t.stato, t.motivo"


def _voce(r) -> Voce:
    return Voce(r["sha256"], lg.dhash_dal_database(r["dhash"]), r["stato"], r["motivo"])


class ImmaginiTrappolaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get(self, sha256: str) -> Voce | None:
        r = await self._pool.fetchrow(f"SELECT {_COLONNE} FROM immagini_trappola t WHERE t.sha256 = $1", bytes.fromhex(sha256))
        return _voce(r) if r else None

    async def valida_per_server(self, sha256: str, guild_id: int) -> Voce | None:
        """La voce se vale in questo server: globale, oppure candidata segnalata da lui."""
        r = await self._pool.fetchrow(
            f"SELECT {_COLONNE} FROM immagini_trappola t WHERE t.sha256 = $1 AND (t.stato = ANY($3::text[]) OR "
            "(t.stato = 'candidata' AND EXISTS (SELECT 1 FROM immagini_trappola_segnalazioni s "
            "WHERE s.sha256 = t.sha256 AND s.guild_id = $2)))",
            bytes.fromhex(sha256), guild_id, list(lg.STATI_GLOBALI + (lg.APPROVATA,)),
        )
        return _voce(r) if r else None

    async def globali(self) -> list[Voce]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM immagini_trappola t WHERE t.stato = ANY($1::text[]) AND t.dhash IS NOT NULL",
            list(lg.STATI_GLOBALI),
        )
        return [_voce(r) for r in righe]

    async def del_server(self, guild_id: int) -> list[Voce]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM immagini_trappola t JOIN immagini_trappola_segnalazioni s ON s.sha256 = t.sha256 "
            "WHERE s.guild_id = $1 AND t.stato = 'candidata' AND t.dhash IS NOT NULL",
            guild_id,
        )
        return [_voce(r) for r in righe]

    async def segnala(
        self, sha256: str, dhash: int | None, motivo: str, guild_id: int, owner_id: int | None
    ) -> Voce | None:
        """
        Un server segnala un'immagine. Nuova: candidata. Con segnalazioni di abbastanza proprietari
        diversi diventa condivisa (owner_id None = il server non conta). Una rifiutata resta tale
        (None). None anche se il server ha gia' troppe candidate.
        """
        chiave = bytes.fromhex(sha256)
        async with self._pool.acquire() as conn, conn.transaction():
            riga = await conn.fetchrow("SELECT stato FROM immagini_trappola WHERE sha256 = $1 FOR UPDATE", chiave)
            if riga is None:
                if await self._candidate_del_server(conn, guild_id) >= lg.MAX_CANDIDATE_PER_SERVER:
                    return None
                await conn.execute(
                    "INSERT INTO immagini_trappola (sha256, dhash, stato, motivo) VALUES ($1, $2, 'candidata', $3) "
                    "ON CONFLICT (sha256) DO NOTHING",
                    chiave, lg.dhash_a_database(dhash), motivo[: lg.MAX_MOTIVO],
                )
                stato = lg.CANDIDATA
            else:
                stato = riga["stato"]
                if stato == lg.RIFIUTATA:
                    return None
                await conn.execute(
                    "UPDATE immagini_trappola SET dhash = COALESCE(dhash, $2) WHERE sha256 = $1", chiave, lg.dhash_a_database(dhash)
                )
            await conn.execute(
                "INSERT INTO immagini_trappola_segnalazioni (sha256, guild_id, owner_id) VALUES ($1, $2, $3) "
                "ON CONFLICT (sha256, guild_id) DO UPDATE SET owner_id = EXCLUDED.owner_id",
                chiave, guild_id, owner_id,
            )
            diversi = await conn.fetchval(
                "SELECT count(DISTINCT owner_id) FROM immagini_trappola_segnalazioni WHERE sha256 = $1 AND owner_id IS NOT NULL AND owner_id <> 0",
                chiave,
            )
            nuovo = lg.stato_dopo_segnalazione(stato, diversi)
            if nuovo != stato:
                await conn.execute("UPDATE immagini_trappola SET stato = $2, aggiornata_il = now() WHERE sha256 = $1", chiave, nuovo)
        return await self.get(sha256)

    @staticmethod
    async def _candidate_del_server(conn, guild_id: int) -> int:
        return await conn.fetchval(
            "SELECT count(*) FROM immagini_trappola_segnalazioni s JOIN immagini_trappola t ON t.sha256 = s.sha256 "
            "WHERE s.guild_id = $1 AND t.stato = 'candidata'",
            guild_id,
        )

    async def aggiungi(self, sha256: str, dhash: int | None, motivo: str) -> None:
        """L'owner del bot aggiunge direttamente un'immagine certa."""
        await self._pool.execute(
            "INSERT INTO immagini_trappola (sha256, dhash, stato, motivo) VALUES ($1, $2, 'approvata', $3) "
            "ON CONFLICT (sha256) DO UPDATE SET stato = 'approvata', dhash = COALESCE(EXCLUDED.dhash, immagini_trappola.dhash), "
            "aggiornata_il = now()",
            bytes.fromhex(sha256), lg.dhash_a_database(dhash), motivo[: lg.MAX_MOTIVO],
        )

    async def per_prefisso(self, prefisso: str) -> list[str]:
        """Le impronte che iniziano cosi' (al massimo 2: basta per dire se e' ambiguo)."""
        righe = await self._pool.fetch(
            "SELECT encode(sha256, 'hex') AS sha256 FROM immagini_trappola WHERE encode(sha256, 'hex') LIKE $1 LIMIT 2",
            prefisso + "%",
        )
        return [r["sha256"] for r in righe]

    async def imposta_stato(self, sha256: str, stato: str) -> bool:
        esito = await self._pool.execute(
            "UPDATE immagini_trappola SET stato = $2, aggiornata_il = now() WHERE sha256 = $1", bytes.fromhex(sha256), stato
        )
        return esito.endswith(" 1")

    async def elenca(self, stato: str, limite: int = 25) -> list[Voce]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM immagini_trappola t LEFT JOIN immagini_trappola_segnalazioni s ON s.sha256 = t.sha256 "
            "WHERE t.stato = $1 GROUP BY t.sha256 ORDER BY count(s.guild_id) DESC, t.creata_il LIMIT $2",
            stato, limite,
        )
        return [_voce(r) for r in righe]

    async def conta(self) -> dict[str, int]:
        righe = await self._pool.fetch("SELECT stato, count(*) AS n FROM immagini_trappola GROUP BY stato")
        return {r["stato"]: r["n"] for r in righe}


def _get_pool():
    from core.database import db

    return db.pool


immagini_trappola_repo = ImmaginiTrappolaRepository(pool_provider=_get_pool)
