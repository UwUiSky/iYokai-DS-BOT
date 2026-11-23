"""
core/repositories/tela_repo.py
==============================
La tela di pixel del server: caselle, pausa per persona, blocchi e impostazioni. Mettere un pixel è una sola
transazione: la riga della persona si blocca (`FOR UPDATE`), così due pixel insieme della stessa persona non saltano
la pausa; la casella è una riga con chiave (server, x, y), quindi due pixel insieme sulla stessa casella lasciano
una riga sola (vince l'ultimo). Le monete per accorciare la pausa escono con una UPDATE condizionata nella stessa
transazione. Si tiene chi ha messo ogni pixel.
Funzioni coperte: FUN-013, FUN-014
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import asyncpg

from core import tela_logic as tl
from core.repositories.leveling_repo import spend_coins_in


class Esito(str, Enum):
    OK = "ok"
    PAUSA = "pausa"
    POCHE = "poche"
    BLOCCATO = "bloccato"


@dataclass(frozen=True)
class Impostazioni:
    pubblica: bool = False
    pausa_secondi: int = tl.PAUSA_BASE
    costo_minuto: int = tl.COSTO_MINUTO_BASE


@dataclass(frozen=True)
class Risultato:
    esito: Esito
    resta: float = 0.0  # secondi di pausa rimasti (PAUSA) o prima del pagamento
    costo: int = 0  # monete pagate (OK) o necessarie (POCHE, PAUSA con pagamento possibile)


@dataclass(frozen=True)
class Pixel:
    colore: int
    user_id: int
    messo_il: datetime


class TelaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- impostazioni
    async def impostazioni(self, guild_id: int) -> Impostazioni:
        r = await self._pool.fetchrow(
            "SELECT pubblica, pausa_secondi, costo_minuto FROM tela_impostazioni WHERE guild_id = $1", guild_id
        )
        return Impostazioni(r["pubblica"], r["pausa_secondi"], r["costo_minuto"]) if r else Impostazioni()

    async def imposta(self, guild_id: int, *, pausa_secondi: int | None = None, costo_minuto: int | None = None,
                      pubblica: bool | None = None) -> Impostazioni:
        if pausa_secondi is not None and not tl.PAUSA_MIN <= pausa_secondi <= tl.PAUSA_MAX:
            raise ValueError("Pausa fuori misura.")
        if costo_minuto is not None and not 0 <= costo_minuto <= tl.COSTO_MINUTO_MAX:
            raise ValueError("Costo fuori misura.")
        r = await self._pool.fetchrow(
            "INSERT INTO tela_impostazioni (guild_id, pausa_secondi, costo_minuto, pubblica) "
            "VALUES ($1, COALESCE($2::int, $5::int), COALESCE($3::int, $6::int), COALESCE($4::boolean, FALSE)) "
            "ON CONFLICT (guild_id) DO UPDATE SET pausa_secondi = COALESCE($2::int, tela_impostazioni.pausa_secondi), "
            "costo_minuto = COALESCE($3::int, tela_impostazioni.costo_minuto), pubblica = COALESCE($4::boolean, tela_impostazioni.pubblica) "
            "RETURNING pubblica, pausa_secondi, costo_minuto",
            guild_id, pausa_secondi, costo_minuto, pubblica, tl.PAUSA_BASE, tl.COSTO_MINUTO_BASE,
        )
        return Impostazioni(r["pubblica"], r["pausa_secondi"], r["costo_minuto"])

    # ---------------------------------------------------------------- pixel
    async def colora(self, guild_id: int, user_id: int, x: int, y: int, colore: int, accorcia: bool = False) -> Risultato:
        """Mette il pixel se la persona non è bloccata e ha finito la pausa (o paga per saltarla)."""
        if not tl.coordinate_valide(x, y) or not tl.colore_valido(colore):
            raise ValueError("Casella o colore non validi.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                imp = await conn.fetchrow(
                    "SELECT pausa_secondi, costo_minuto FROM tela_impostazioni WHERE guild_id = $1", guild_id
                )
                pausa = imp["pausa_secondi"] if imp else tl.PAUSA_BASE
                costo_minuto = imp["costo_minuto"] if imp else tl.COSTO_MINUTO_BASE
                await conn.execute(
                    "INSERT INTO tela_utenti (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, user_id
                )
                riga = await conn.fetchrow(
                    "SELECT bloccato, GREATEST(0, EXTRACT(EPOCH FROM (ultimo_at + make_interval(secs => $3) - now()))) AS resta "
                    "FROM tela_utenti WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id, float(pausa),
                )
                if riga["bloccato"]:
                    return Risultato(Esito.BLOCCATO)
                resta = float(riga["resta"] or 0)
                pagato = 0
                if resta > 0:
                    costo = tl.costo_accorciare(resta, costo_minuto)
                    if not accorcia or costo <= 0:
                        return Risultato(Esito.PAUSA, resta, costo)
                    if not await spend_coins_in(conn, guild_id, user_id, costo, motivo="tela"):
                        return Risultato(Esito.POCHE, resta, costo)
                    pagato = costo
                await conn.execute(
                    "INSERT INTO tela_pixel (guild_id, x, y, colore, user_id) VALUES ($1, $2, $3, $4, $5) "
                    "ON CONFLICT (guild_id, x, y) DO UPDATE SET colore = EXCLUDED.colore, user_id = EXCLUDED.user_id, messo_il = now()",
                    guild_id, x, y, colore, user_id,
                )
                await conn.execute(
                    "UPDATE tela_utenti SET ultimo_at = now(), pixel_messi = pixel_messi + 1 WHERE guild_id = $1 AND user_id = $2",
                    guild_id, user_id,
                )
                return Risultato(Esito.OK, resta, pagato)

    async def attesa(self, guild_id: int, user_id: int) -> tuple[float, bool, int]:
        """(secondi di pausa rimasti, bloccato, pixel messi)."""
        pausa = (await self.impostazioni(guild_id)).pausa_secondi
        r = await self._pool.fetchrow(
            "SELECT bloccato, pixel_messi, GREATEST(0, EXTRACT(EPOCH FROM (ultimo_at + make_interval(secs => $3) - now()))) AS resta "
            "FROM tela_utenti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id, float(pausa),
        )
        return (float(r["resta"] or 0), r["bloccato"], r["pixel_messi"]) if r else (0.0, False, 0)

    async def pixel(self, guild_id: int, x: int, y: int) -> Pixel | None:
        r = await self._pool.fetchrow(
            "SELECT colore, user_id, messo_il FROM tela_pixel WHERE guild_id = $1 AND x = $2 AND y = $3", guild_id, x, y
        )
        return Pixel(r["colore"], r["user_id"], r["messo_il"]) if r else None

    async def caselle(self, guild_id: int, x0: int, y0: int, lato: int) -> list[tuple[int, int, int]]:
        righe = await self._pool.fetch(
            "SELECT x, y, colore FROM tela_pixel WHERE guild_id = $1 AND x >= $2 AND x < $3 AND y >= $4 AND y < $5",
            guild_id, x0, x0 + lato, y0, y0 + lato,
        )
        return [(r["x"], r["y"], r["colore"]) for r in righe]

    async def conta(self, guild_id: int) -> int:
        return await self._pool.fetchval("SELECT count(*) FROM tela_pixel WHERE guild_id = $1", guild_id)

    # ---------------------------------------------------------------- moderazione (FUN-014)
    async def azzera(self, guild_id: int) -> int:
        """Toglie tutti i pixel del server. Restituisce quanti."""
        esito = await self._pool.execute("DELETE FROM tela_pixel WHERE guild_id = $1", guild_id)
        return int(esito.split()[-1])

    async def togli_utente(self, guild_id: int, user_id: int) -> int:
        """Toglie tutti i pixel messi da una persona. Restituisce quanti."""
        esito = await self._pool.execute("DELETE FROM tela_pixel WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
        return int(esito.split()[-1])

    async def imposta_blocco(self, guild_id: int, user_id: int, bloccato: bool) -> bool:
        """Blocca o sblocca. Restituisce True se lo stato è cambiato."""
        r = await self._pool.fetchrow(
            "WITH prima AS (SELECT bloccato FROM tela_utenti WHERE guild_id = $1 AND user_id = $2), "
            "ora AS (INSERT INTO tela_utenti (guild_id, user_id, bloccato) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET bloccato = $3 RETURNING 1) "
            "SELECT COALESCE((SELECT bloccato FROM prima), FALSE) AS prima, (SELECT count(*) FROM ora) AS fatto",
            guild_id, user_id, bloccato,
        )
        return bool(r["prima"]) != bloccato

    async def e_bloccato(self, guild_id: int, user_id: int) -> bool:
        return bool(await self._pool.fetchval(
            "SELECT bloccato FROM tela_utenti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id))


def _get_pool():
    from core.database import db

    return db.pool


tela_repo = TelaRepository(pool_provider=_get_pool)
