"""
core/repositories/pesca_repo.py
===============================
Pesca avanzata: profilo (abilità, perle, esche, canna), pass stagionale, rete per la pesca automatica, storico.
Ogni acquisto di attrezzi e ogni sblocco è una UPDATE condizionata sul profilo; la rete e il pass si riscuotono
una volta sola perché la condizione sta nella stessa scrittura.
Funzioni coperte: ECO-135, ECO-136, ECO-137, ECO-139, ECO-140, ECO-141
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import asyncpg

from core.animali_avanzati_logic import (
    ABILITA, CANNA_MAX, LIVELLI_STAGIONE, PERLE_CANNA, PERLE_ESCA, PERLE_RETE, RETE_PAUSA_S, SOGLIA_STAGIONE,
    livello_stagione, premio_stagione, punti_abilita, stagione,
)
from core.repositories.animali_repo import MAX_PESCI_DEPOSITO, registra_cattura
from core.repositories.leveling_repo import add_coins_in


@dataclass(frozen=True)
class ProfiloPesca:
    lanci: int = 0
    pescati: int = 0
    perle: int = 0
    esche: int = 0
    canna: int = 0
    rete_at: object = None
    abilita: frozenset = frozenset()


class PescaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def profilo(self, guild_id: int, user_id: int) -> ProfiloPesca:
        r = await self._pool.fetchrow(
            "SELECT lanci, pescati, perle, esche, canna, rete_at, abilita FROM economia_pesca_profilo WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        if r is None:
            return ProfiloPesca()
        return ProfiloPesca(r["lanci"], r["pescati"], r["perle"], r["esche"], r["canna"], r["rete_at"], frozenset(a for a in r["abilita"].split(",") if a in ABILITA))

    async def punti_liberi(self, guild_id: int, user_id: int) -> int:
        """ECO-135: punti delle sfide (pesci presi e specie trovate) meno quelli già spesi."""
        p = await self.profilo(guild_id, user_id)
        visti = await self._pool.fetchval("SELECT count(*) FROM economia_pesci_visti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
        return punti_abilita(p.pescati, visti) - sum(ABILITA[a] for a in p.abilita)

    async def sblocca(self, guild_id: int, user_id: int, abilita: str) -> str:
        """«ok», «gia», «poche» (punti) o «sconosciuta». Il profilo si blocca: due sblocchi insieme non spendono due volte."""
        if abilita not in ABILITA:
            return "sconosciuta"
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("INSERT INTO economia_pesca_profilo (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, user_id)
                r = await conn.fetchrow("SELECT pescati, abilita FROM economia_pesca_profilo WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id)
                avute = {a for a in r["abilita"].split(",") if a in ABILITA}
                if abilita in avute:
                    return "gia"
                visti = await conn.fetchval("SELECT count(*) FROM economia_pesci_visti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                if punti_abilita(r["pescati"], visti) - sum(ABILITA[a] for a in avute) < ABILITA[abilita]:
                    return "poche"
                await conn.execute(
                    "UPDATE economia_pesca_profilo SET abilita = $3 WHERE guild_id = $1 AND user_id = $2", guild_id, user_id, ",".join(sorted(avute | {abilita}))
                )
                return "ok"

    async def compra_attrezzo(self, guild_id: int, user_id: int, attrezzo: str) -> tuple[str, int]:
        """Con le perle: «esca» (5), «rete» (30, una volta), «canna» (livelli 1-3). («ok»|«poche»|«gia»|«massimo», costo)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("INSERT INTO economia_pesca_profilo (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, user_id)
                r = await conn.fetchrow("SELECT canna, rete_at FROM economia_pesca_profilo WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id)
                if attrezzo == "esca":
                    costo, effetto = PERLE_ESCA, "esche = esche + 1"
                elif attrezzo == "rete":
                    if r["rete_at"] is not None:
                        return "gia", 0
                    costo, effetto = PERLE_RETE, "rete_at = now()"
                elif attrezzo == "canna":
                    if r["canna"] >= CANNA_MAX:
                        return "massimo", 0
                    costo, effetto = PERLE_CANNA[r["canna"]], "canna = canna + 1"
                else:
                    raise ValueError("Attrezzo sconosciuto.")
                ok = await conn.fetchval(
                    f"UPDATE economia_pesca_profilo SET perle = perle - $3, {effetto} WHERE guild_id = $1 AND user_id = $2 AND perle >= $3 RETURNING 1",
                    guild_id, user_id, costo,
                )
                return ("ok" if ok else "poche"), costo

    async def stagione_stato(self, guild_id: int, user_id: int, oggi: date) -> tuple[int, int]:
        """(punti del mese, livelli già riscossi)."""
        r = await self._pool.fetchrow(
            "SELECT punti, riscossi FROM economia_pesca_stagione WHERE guild_id = $1 AND user_id = $2 AND stagione = $3", guild_id, user_id, stagione(oggi)
        )
        return (r["punti"], r["riscossi"]) if r else (0, 0)

    async def riscuoti_stagione(self, guild_id: int, user_id: int, oggi: date) -> int | None:
        """Un livello alla volta (traccia gratuita). Restituisce le monete, None se non c'è un livello da riscuotere."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                r = await conn.fetchrow(
                    "UPDATE economia_pesca_stagione SET riscossi = riscossi + 1 WHERE guild_id = $1 AND user_id = $2 AND stagione = $3 "
                    "AND riscossi < $4 AND punti >= (riscossi + 1) * $5 RETURNING riscossi",
                    guild_id, user_id, stagione(oggi), LIVELLI_STAGIONE, SOGLIA_STAGIONE,
                )
                if r is None:
                    return None
                monete = premio_stagione(r["riscossi"])
                await add_coins_in(conn, guild_id, user_id, monete, classifica=False, motivo="pesca_stagione")
                return monete

    async def riscuoti_rete(self, guild_id: int, user_id: int, oggi: date, estrai) -> list[str | None] | None:
        """
        ECO-140: la rete ha pescato mentre eri via (un lancio all'ora, al massimo 12). `estrai(n)` dà le specie (o None).
        Il tempo passato si legge e si azzera nella stessa scrittura. None se non hai la rete o non è passata un'ora.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                r = await conn.fetchrow(
                    "SELECT EXTRACT(EPOCH FROM now() - rete_at) AS s FROM economia_pesca_profilo WHERE guild_id = $1 AND user_id = $2 "
                    "AND rete_at IS NOT NULL FOR UPDATE", guild_id, user_id,
                )
                if r is None or r["s"] < RETE_PAUSA_S:
                    return None
                from core.animali_avanzati_logic import lanci_rete

                n = lanci_rete(float(r["s"]))
                tot = await conn.fetchval("SELECT COALESCE(SUM(quantita), 0) FROM economia_pesci WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                prese = []
                for specie in estrai(n):
                    if specie is not None and tot < MAX_PESCI_DEPOSITO + 100:
                        tot += 1
                        await conn.execute(
                            "INSERT INTO economia_pesci (guild_id, user_id, specie, quantita) VALUES ($1, $2, $3, 1) "
                            "ON CONFLICT (guild_id, user_id, specie) DO UPDATE SET quantita = economia_pesci.quantita + 1", guild_id, user_id, specie,
                        )
                        await conn.execute(
                            "INSERT INTO economia_pesci_visti (guild_id, user_id, specie) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", guild_id, user_id, specie
                        )
                        await registra_cattura(conn, guild_id, user_id, specie, oggi)
                        prese.append(specie)
                    else:
                        prese.append(None)
                await conn.execute("UPDATE economia_pesca_profilo SET rete_at = now() WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                return prese

    async def storico(self, guild_id: int, user_id: int, limite: int = 15) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT quando, tipo, specie, valore FROM economia_pesca_storico WHERE guild_id = $1 AND user_id = $2 ORDER BY id DESC LIMIT $3",
            guild_id, user_id, min(max(1, limite), 25),
        )


def _get_pool():
    from core.database import db

    return db.pool


pesca_repo = PescaRepository(pool_provider=_get_pool)
