"""
core/repositories/music_cartella_repo.py
========================================
Tabelle music_cartella_brani (elenco dei brani della cartella dell'owner) e music_owner_impostazioni
(impostazioni globali dell'owner per la musica: anteprime agli utenti, paese delle ricerche).
Funzioni coperte: SPEC §9 (catalogo MUS-018, MUS-015)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.music_cartella_logic import BranoCartella, MAX_FILE

CHIAVE_ANTEPRIME = "anteprime_utenti"
CHIAVE_PAESE = "paese_globale"


@dataclass(frozen=True)
class BranoSalvato:
    id: int
    percorso: str
    titolo: str
    durata_ms: int | None


class MusicCartellaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def sincronizza(self, brani: list[BranoCartella]) -> tuple[int, int, int]:
        """
        Allinea la tabella alla scansione, in una transazione: (nuovi, tolti, cambiati). Un brano con lo
        stesso peso e la stessa data mantiene titolo e durata gia' letti; se cambia, si riparte dal nome del file.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(7170018)")
                esistenti = {
                    r["percorso"]: (r["dimensione"], r["modificato_ns"])
                    for r in await conn.fetch("SELECT percorso, dimensione, modificato_ns FROM music_cartella_brani")
                }
                nuovi = cambiati = 0
                for b in brani[:MAX_FILE]:
                    prima = esistenti.get(b.percorso)
                    if prima is None:
                        nuovi += 1
                        await conn.execute(
                            "INSERT INTO music_cartella_brani (percorso, titolo, dimensione, modificato_ns) "
                            "VALUES ($1, $2, $3, $4)", b.percorso, b.titolo, b.dimensione, b.modificato_ns,
                        )
                    elif prima != (b.dimensione, b.modificato_ns):
                        cambiati += 1
                        await conn.execute(
                            "UPDATE music_cartella_brani SET titolo = $2, durata_ms = NULL, dimensione = $3, "
                            "modificato_ns = $4, visto_il = now() WHERE percorso = $1",
                            b.percorso, b.titolo, b.dimensione, b.modificato_ns,
                        )
                presenti = [b.percorso for b in brani[:MAX_FILE]]
                esito = await conn.execute(
                    "DELETE FROM music_cartella_brani WHERE NOT (percorso = ANY($1::text[]))", presenti
                )
                return nuovi, int(esito.split()[-1]), cambiati

    async def elenco(self) -> list[BranoSalvato]:
        righe = await self._pool.fetch(
            "SELECT id, percorso, titolo, durata_ms FROM music_cartella_brani ORDER BY lower(titolo), id LIMIT $1",
            MAX_FILE,
        )
        return [BranoSalvato(r["id"], r["percorso"], r["titolo"], r["durata_ms"]) for r in righe]

    async def cerca(self, testo: str, limite: int = 25) -> list[BranoSalvato]:
        """Per l'autocompletamento: titolo che contiene il testo (il testo e' un parametro, mai SQL)."""
        righe = await self._pool.fetch(
            "SELECT id, percorso, titolo, durata_ms FROM music_cartella_brani "
            "WHERE position(lower($1) in lower(titolo)) > 0 ORDER BY lower(titolo), id LIMIT $2",
            testo[:100], limite,
        )
        return [BranoSalvato(r["id"], r["percorso"], r["titolo"], r["durata_ms"]) for r in righe]

    async def get(self, brano_id: int) -> BranoSalvato | None:
        r = await self._pool.fetchrow(
            "SELECT id, percorso, titolo, durata_ms FROM music_cartella_brani WHERE id = $1", brano_id
        )
        return BranoSalvato(r["id"], r["percorso"], r["titolo"], r["durata_ms"]) if r else None

    async def conta(self) -> int:
        return int(await self._pool.fetchval("SELECT count(*) FROM music_cartella_brani"))

    async def imposta_dettagli(self, brano_id: int, titolo: str, durata_ms: int | None) -> None:
        await self._pool.execute(
            "UPDATE music_cartella_brani SET titolo = $2, durata_ms = $3 WHERE id = $1", brano_id, titolo[:100], durata_ms
        )

    # ---- impostazioni globali dell'owner ----
    async def leggi_impostazione(self, chiave: str) -> str | None:
        return await self._pool.fetchval("SELECT valore FROM music_owner_impostazioni WHERE chiave = $1", chiave)

    async def scrivi_impostazione(self, chiave: str, valore: str | None, owner_id: int) -> None:
        """`None` toglie la scelta (torna il predefinito)."""
        if valore is None:
            await self._pool.execute("DELETE FROM music_owner_impostazioni WHERE chiave = $1", chiave)
            return
        await self._pool.execute(
            "INSERT INTO music_owner_impostazioni (chiave, valore, cambiata_da) VALUES ($1, $2, $3) "
            "ON CONFLICT (chiave) DO UPDATE SET valore = $2, cambiata_da = $3, cambiata_il = now()",
            chiave, valore, owner_id,
        )


def _get_pool():
    from core.database import db
    return db.pool


music_cartella_repo = MusicCartellaRepository(pool_provider=_get_pool)
