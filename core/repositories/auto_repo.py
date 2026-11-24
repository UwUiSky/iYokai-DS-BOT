"""
core/repositories/auto_repo.py
==============================
Garage delle auto da collezione e foto delle proprie auto (FUN-017). Ogni movimento di monete (acquisto,
potenziamento) sta nella stessa transazione della modifica del garage, con una UPDATE condizionata sul saldo: due
clic insieme non pagano due volte e non danno due livelli. Della foto si conserva solo la copia PNG ricodificata (D74).
Funzioni coperte: FUN-017
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import asyncpg

from core import auto_logic as al
from core.repositories.leveling_repo import spend_coins_in

MAX_BYTE_FOTO = 2 * 1024 * 1024


class Esito(str, Enum):
    OK = "ok"
    GIA = "gia"  # già nel garage
    POCHE = "poche"
    MANCA = "manca"  # l'auto non è nel garage
    MASSIMO = "massimo"


@dataclass(frozen=True)
class Auto:
    id: int
    user_id: int
    modello: str
    motore: int
    assetto: int
    gomme: int
    corse: int
    vinte: int
    con_foto: bool = False
    sha_foto: str | None = None

    @property
    def livelli(self) -> tuple[int, int, int]:
        return self.motore, self.assetto, self.gomme


def _auto(r) -> Auto:
    return Auto(r["id"], r["user_id"], r["modello"], r["motore"], r["assetto"], r["gomme"], r["corse"], r["vinte"],
                bool(r["sha256"]), r["sha256"])


_SELEZIONE = (
    "SELECT g.id, g.user_id, g.modello, g.motore, g.assetto, g.gomme, g.corse, g.vinte, f.sha256 "
    "FROM fun_auto_garage g LEFT JOIN fun_auto_foto f ON f.auto_id = g.id "
)


class AutoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- garage
    async def garage(self, guild_id: int, user_id: int) -> list[Auto]:
        righe = await self._pool.fetch(_SELEZIONE + "WHERE g.guild_id = $1 AND g.user_id = $2 ORDER BY g.id", guild_id, user_id)
        return [_auto(r) for r in righe]

    async def auto(self, guild_id: int, user_id: int, modello: str) -> Auto | None:
        r = await self._pool.fetchrow(_SELEZIONE + "WHERE g.guild_id = $1 AND g.user_id = $2 AND g.modello = $3", guild_id, user_id, modello)
        return _auto(r) if r else None

    async def compra(self, guild_id: int, user_id: int, modello: str) -> Esito:
        """Mette l'auto nel garage e toglie il prezzo, insieme. Con un'auto già posseduta o senza monete non cambia niente."""
        m = al.trova(modello)
        if m is None:
            raise ValueError(modello)
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    nuova = await conn.fetchval(
                        "INSERT INTO fun_auto_garage (guild_id, user_id, modello) VALUES ($1, $2, $3) "
                        "ON CONFLICT (guild_id, user_id, modello) DO NOTHING RETURNING id", guild_id, user_id, modello,
                    )
                    if nuova is None:
                        return Esito.GIA
                    if not await spend_coins_in(conn, guild_id, user_id, m.prezzo, motivo="auto"):
                        raise _Annulla(Esito.POCHE)  # l'eccezione annulla anche la riga appena messa
                    return Esito.OK
        except _Annulla as e:
            return e.esito

    async def potenzia(self, guild_id: int, user_id: int, modello: str, parte: str) -> tuple[Esito, int, int]:
        """(esito, livello dopo, costo). La riga si blocca: due potenziamenti insieme vanno uno dopo l'altro e ognuno paga il suo."""
        if parte not in al.PARTI:
            raise ValueError(parte)
        m = al.trova(modello)
        if m is None:
            raise ValueError(modello)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                riga = await conn.fetchrow(
                    f"SELECT id, {parte} AS livello FROM fun_auto_garage "  # `parte` viene dall'elenco fisso PARTI
                    "WHERE guild_id = $1 AND user_id = $2 AND modello = $3 FOR UPDATE", guild_id, user_id, modello,
                )
                if riga is None:
                    return Esito.MANCA, 0, 0
                livello = riga["livello"]
                if livello >= al.LIVELLO_MASSIMO:
                    return Esito.MASSIMO, livello, 0
                costo = al.costo_potenziamento(m.rarita, livello)
                if not await spend_coins_in(conn, guild_id, user_id, costo, motivo="auto"):
                    return Esito.POCHE, livello, costo
                await conn.execute(f"UPDATE fun_auto_garage SET {parte} = {parte} + 1 WHERE id = $1", riga["id"])
                return Esito.OK, livello + 1, costo

    async def registra_gara(self, guild_id: int, corsa: list[tuple[int, bool]]) -> None:
        """`corsa`: (id dell'auto, ha vinto) per ogni auto vera che ha corso (quella del banco non c'è)."""
        if not corsa:
            return
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for auto_id, vinta in sorted(corsa):
                    await conn.execute(
                        "UPDATE fun_auto_garage SET corse = corse + 1, vinte = vinte + $3 WHERE id = $1 AND guild_id = $2",
                        auto_id, guild_id, 1 if vinta else 0,
                    )

    # ---------------------------------------------------------------- foto
    async def imposta_foto(self, guild_id: int, user_id: int, modello: str, png: bytes, sha256: str, controllata: bool = False) -> bool:
        """Salva (o sostituisce) la foto dell'auto. False se l'auto non è nel garage. Solo copie PNG già ricodificate.
        `controllata`: la foto ha già passato il controllo dei contenuti per adulti (FUN-017, D122)."""
        if not png or len(png) > MAX_BYTE_FOTO:
            raise ValueError("Foto vuota o troppo grande.")
        return bool(await self._pool.fetchval(
            "WITH a AS (SELECT id FROM fun_auto_garage WHERE guild_id = $1 AND user_id = $2 AND modello = $3), "
            "f AS (INSERT INTO fun_auto_foto (auto_id, guild_id, user_id, png, sha256, controllata_il) "
            "SELECT id, $1, $2, $4, $5, CASE WHEN $6 THEN now() END FROM a ON CONFLICT (auto_id) DO UPDATE SET png = EXCLUDED.png, "
            "sha256 = EXCLUDED.sha256, caricata_il = now(), controllata_il = EXCLUDED.controllata_il RETURNING 1) SELECT 1 FROM f",
            guild_id, user_id, modello, png, sha256, controllata,
        ))

    async def foto(self, guild_id: int, user_id: int, modello: str) -> tuple[bytes, str, bool] | None:
        """(PNG, impronta, già controllata) oppure None."""
        r = await self._pool.fetchrow(
            "SELECT f.png, f.sha256, f.controllata_il IS NOT NULL AS controllata FROM fun_auto_foto f "
            "JOIN fun_auto_garage g ON g.id = f.auto_id WHERE g.guild_id = $1 AND g.user_id = $2 AND g.modello = $3",
            guild_id, user_id, modello,
        )
        return (bytes(r["png"]), r["sha256"], r["controllata"]) if r else None

    async def segna_controllata(self, guild_id: int, user_id: int, modello: str, sha256: str) -> None:
        """La foto con quell'impronta ha passato il controllo (una foto cambiata nel frattempo non si segna)."""
        await self._pool.execute(
            "UPDATE fun_auto_foto SET controllata_il = now() WHERE sha256 = $4 AND auto_id IN "
            "(SELECT id FROM fun_auto_garage WHERE guild_id = $1 AND user_id = $2 AND modello = $3)",
            guild_id, user_id, modello, sha256,
        )

    async def togli_foto(self, guild_id: int, user_id: int, modello: str | None = None) -> int:
        """Toglie la foto di un'auto (o di tutte quelle dell'utente se `modello` è None). Restituisce quante."""
        if modello is None:
            esito = await self._pool.execute("DELETE FROM fun_auto_foto WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
        else:
            esito = await self._pool.execute(
                "DELETE FROM fun_auto_foto WHERE auto_id IN (SELECT id FROM fun_auto_garage WHERE guild_id = $1 AND user_id = $2 AND modello = $3)",
                guild_id, user_id, modello,
            )
        return int(esito.split()[-1])


class _Annulla(Exception):
    def __init__(self, esito: Esito) -> None:
        self.esito = esito


def _get_pool():
    from core.database import db

    return db.pool


auto_repo = AutoRepository(pool_provider=_get_pool)
