"""
core/repositories/sociale_repo.py
=================================
Blocchi tra utenti, amici, matrimoni, prestigio e azzeramento dei propri dati di gioco. Le coppie stanno in una riga
ordinata (a < b): una richiesta accettata scrive la riga una volta sola (INSERT ... ON CONFLICT DO NOTHING), il
matrimonio si paga da entrambi nella stessa transazione, il prestigio azzera e sale di un livello con la riga bloccata.
Funzioni coperte: ECO-148, ECO-149, ECO-153, ECO-154, ECO-155, ECO-159
"""

from __future__ import annotations

import asyncpg

from core.repositories.guild_chest_repo import deposit_in
from core.repositories.leveling_repo import spend_coins_in

MAX_BLOCCHI = 100
MAX_AMICI = 50
COSTO_MATRIMONIO = 200  # a testa, alla cassa del server
GIORNI_SENZA_MANTENIMENTO = 14
PRESTIGIO_MASSIMO = 5
BONUS_PRESTIGIO = 5  # % al lavoro e al premio per livello
SOGLIA_PRESTIGIO = 10_000  # patrimonio (contanti + banca) per il livello 1; poi si moltiplica per il livello


def coppia(x: int, y: int) -> tuple[int, int]:
    if x == y:
        raise ValueError("Serve una coppia di persone diverse.")
    return (x, y) if x < y else (y, x)


def soglia_prestigio(livello_attuale: int) -> int | None:
    if not 0 <= livello_attuale < PRESTIGIO_MASSIMO:
        return None
    return SOGLIA_PRESTIGIO * (livello_attuale + 1)


class SocialeRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- blocchi (ECO-155)
    async def blocca(self, user_id: int, bloccato_id: int) -> str:
        """«ok», «gia» o «pieno» (massimo 100). Mai se stessi."""
        if user_id == bloccato_id:
            raise ValueError("Non ci si blocca da soli.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", user_id)
                if await conn.fetchval("SELECT count(*) FROM economia_blocchi WHERE user_id = $1", user_id) >= MAX_BLOCCHI:
                    return "pieno"
                nuovo = await conn.fetchval(
                    "INSERT INTO economia_blocchi (user_id, bloccato_id) VALUES ($1, $2) ON CONFLICT DO NOTHING RETURNING 1", user_id, bloccato_id
                )
                return "ok" if nuovo else "gia"

    async def sblocca(self, user_id: int, bloccato_id: int) -> bool:
        return (await self._pool.execute(
            "DELETE FROM economia_blocchi WHERE user_id = $1 AND bloccato_id = $2", user_id, bloccato_id)).endswith(" 1")

    async def ha_bloccato(self, user_id: int, altro_id: int) -> bool:
        """Vero se `user_id` ha bloccato `altro_id`: niente richieste, regali o inviti da lui."""
        return bool(await self._pool.fetchval(
            "SELECT 1 FROM economia_blocchi WHERE user_id = $1 AND bloccato_id = $2", user_id, altro_id))

    async def elenco_blocchi(self, user_id: int) -> list[int]:
        return [r["bloccato_id"] for r in await self._pool.fetch(
            "SELECT bloccato_id FROM economia_blocchi WHERE user_id = $1 ORDER BY bloccato_id LIMIT 100", user_id)]

    # ---------------------------------------------------------------- amici (ECO-154)
    async def aggiungi_amico(self, guild_id: int, x: int, y: int) -> str:
        """«ok», «gia» o «pieno» (50 amici per persona). Il blocco si controlla prima, nel comando."""
        a, b = coppia(x, y)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for u in sorted((x, y)):
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"amici:{guild_id}:{u}")
                for u in (x, y):
                    if await conn.fetchval("SELECT count(*) FROM economia_amici WHERE guild_id = $1 AND (a = $2 OR b = $2)", guild_id, u) >= MAX_AMICI:
                        return "pieno"
                nuovo = await conn.fetchval(
                    "INSERT INTO economia_amici (guild_id, a, b) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING RETURNING 1", guild_id, a, b
                )
                return "ok" if nuovo else "gia"

    async def togli_amico(self, guild_id: int, x: int, y: int) -> bool:
        a, b = coppia(x, y)
        return (await self._pool.execute(
            "DELETE FROM economia_amici WHERE guild_id = $1 AND a = $2 AND b = $3", guild_id, a, b)).endswith(" 1")

    async def sono_amici(self, guild_id: int, x: int, y: int) -> bool:
        if x == y:
            return False
        a, b = coppia(x, y)
        return bool(await self._pool.fetchval("SELECT 1 FROM economia_amici WHERE guild_id = $1 AND a = $2 AND b = $3", guild_id, a, b))

    async def amici_di(self, guild_id: int, user_id: int) -> list[int]:
        righe = await self._pool.fetch(
            "SELECT CASE WHEN a = $2 THEN b ELSE a END AS amico FROM economia_amici WHERE guild_id = $1 AND (a = $2 OR b = $2) ORDER BY 1 LIMIT 50",
            guild_id, user_id,
        )
        return [r["amico"] for r in righe]

    # ---------------------------------------------------------------- matrimonio (ECO-153)
    async def sposa(self, guild_id: int, x: int, y: int) -> str:
        """
        Sposa due persone: ognuna paga COSTO_MATRIMONIO (alla cassa) nella stessa transazione, righe bloccate in ordine di ID.
        «ok», «gia» (uno dei due è già sposato) o «poche».
        """
        a, b = coppia(x, y)
        try:
            return await self._sposa(guild_id, a, b)
        except _Annulla as e:
            return e.args[0]

    async def _sposa(self, guild_id: int, a: int, b: int) -> str:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for u in (a, b):
                    await conn.execute("INSERT INTO leveling_totals (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, u)
                await conn.fetch(
                    "SELECT 1 FROM leveling_totals WHERE guild_id = $1 AND user_id = ANY($2::bigint[]) ORDER BY user_id FOR UPDATE", guild_id, [a, b]
                )
                scaduti = f"mantenuto_at < now() - interval '{GIORNI_SENZA_MANTENIMENTO} days'"  # costante nostra, non dell'utente
                await conn.execute(
                    f"DELETE FROM economia_matrimoni WHERE guild_id = $1 AND (a = ANY($2::bigint[]) OR b = ANY($2::bigint[])) AND {scaduti}", guild_id, [a, b]
                )
                nuovo = await conn.fetchval(
                    "INSERT INTO economia_matrimoni (guild_id, a, b) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING RETURNING 1", guild_id, a, b
                )
                if nuovo is None:
                    raise _Annulla("gia")
                for u in (a, b):
                    if not await spend_coins_in(conn, guild_id, u, COSTO_MATRIMONIO):
                        raise _Annulla("poche")
                    await deposit_in(conn, guild_id, COSTO_MATRIMONIO, "matrimonio")
                return "ok"

    async def coniuge(self, guild_id: int, user_id: int) -> int | None:
        """L'altro sposo, se il matrimonio è tenuto in vita (mantenuto negli ultimi 14 giorni)."""
        return await self._pool.fetchval(
            "SELECT CASE WHEN a = $2 THEN b ELSE a END FROM economia_matrimoni WHERE guild_id = $1 AND (a = $2 OR b = $2) "
            f"AND mantenuto_at >= now() - interval '{GIORNI_SENZA_MANTENIMENTO} days'",
            guild_id, user_id,
        )

    async def mantieni(self, guild_id: int, user_id: int) -> bool:
        return (await self._pool.execute(
            "UPDATE economia_matrimoni SET mantenuto_at = now() WHERE guild_id = $1 AND (a = $2 OR b = $2) "
            f"AND mantenuto_at >= now() - interval '{GIORNI_SENZA_MANTENIMENTO} days'", guild_id, user_id)).endswith(" 1")

    async def divorzia(self, guild_id: int, user_id: int) -> bool:
        return (await self._pool.execute(
            "DELETE FROM economia_matrimoni WHERE guild_id = $1 AND (a = $2 OR b = $2)", guild_id, user_id)).endswith(" 1")

    # ---------------------------------------------------------------- prestigio (ECO-148, 149)
    async def livello_prestigio(self, guild_id: int, user_id: int) -> int:
        return int(await self._pool.fetchval(
            "SELECT livello FROM economia_prestigio WHERE guild_id = $1 AND user_id = $2", guild_id, user_id) or 0)

    async def prestigio(self, guild_id: int, user_id: int) -> tuple[str, int]:
        """
        Ricomincia da capo: servono contanti + banca di almeno la soglia; azzera contanti, banca, potenziamenti e turni
        di lavoro e sale di un livello (bonus permanente). («ok», nuovo livello), («massimo», livello) o («poche», soglia).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("INSERT INTO economia_prestigio (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, user_id)
                livello = await conn.fetchval(
                    "SELECT livello FROM economia_prestigio WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id
                )
                soglia = soglia_prestigio(livello)
                if soglia is None:
                    return "massimo", livello
                tolti = await conn.fetchval(
                    "UPDATE leveling_totals SET coins_total = 0, banca_total = 0 WHERE guild_id = $1 AND user_id = $2 "
                    "AND coins_total + banca_total >= $3 RETURNING 1",
                    guild_id, user_id, soglia,
                )
                if tolti is None:
                    return "poche", soglia
                await conn.execute("DELETE FROM economia_potenziamenti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                await conn.execute("DELETE FROM economia_lavoro WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                await conn.execute(
                    "UPDATE economia_prestigio SET livello = livello + 1 WHERE guild_id = $1 AND user_id = $2 AND livello = $3", guild_id, user_id, livello
                )
                return "ok", livello + 1

    # ---------------------------------------------------------------- azzera i propri dati (ECO-159)
    async def azzera_miei_dati(self, guild_id: int, user_id: int) -> int:
        """Cancella le righe di gioco della persona in questo server (e porta a zero monete e banca). Restituisce le righe toccate."""
        tabelle = (
            "economia_inventario", "economia_animali", "economia_animali_posti", "economia_pesci", "economia_pesci_visti",
            "economia_pesca_giorno", "economia_potenziamenti", "economia_lavoro", "economia_giochi_stat", "economia_depositi",
            "economia_rimborsi", "economia_pause", "economia_prestigio",
        )
        totale = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for t in tabelle:
                    totale += int((await conn.execute(f"DELETE FROM {t} WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)).split()[-1])
                for t in ("economia_amici", "economia_matrimoni"):
                    totale += int((await conn.execute(f"DELETE FROM {t} WHERE guild_id = $1 AND (a = $2 OR b = $2)", guild_id, user_id)).split()[-1])
                totale += int((await conn.execute(
                    "UPDATE leveling_totals SET coins_total = 0, banca_total = 0 WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)).split()[-1])
        return totale


class _Annulla(Exception):
    pass


def _get_pool():
    from core.database import db

    return db.pool


sociale_repo = SocialeRepository(pool_provider=_get_pool)
