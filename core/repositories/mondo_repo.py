"""
core/repositories/mondo_repo.py
===============================
Gettoni (seconda moneta globale), vacanza della serie, diretta, casa, fattoria, personaggi, avventure, borsa finta con
ordini a soglia, vendita automatica, eventi in chat (codice, bonus a tempo, evento raro) e bonus a tempo. Ogni
pagamento e il suo effetto stanno nella stessa transazione; ogni «primo che arriva» è una UPDATE condizionata.
Funzioni coperte: ECO-018, ECO-027, ECO-045, ECO-054, ECO-056, ECO-083, ECO-084, ECO-085, ECO-087, ECO-142, ECO-144, ECO-145, ECO-146, ECO-147
"""

from __future__ import annotations

import random
from datetime import date, datetime, timezone

import asyncpg

from core.mondo_logic import (
    COLTURE, MAX_ORDINI, MAX_QUOTE_PER_TITOLO, MOBILI, PASSO_BORSA_S, POSTI_FATTORIA, SIMBOLI, costo_con_commissione, ordine_scatta,
    paga_diretta, prezzo_dopo, ricavo_con_commissione, serie_diretta,
)
from core.repositories.guild_chest_repo import deposit_in
from core.repositories.leveling_repo import add_coins_in, spend_coins_in

RNG = random.SystemRandom()
COSTO_VACANZA_GIORNO = 20
VACANZA_GIORNI_MAX = 90
MAX_AUTOVENDITE = 5
TUTTO_IL_SERVER = 0  # user_id del bonus a tempo che vale per tutti


class MondoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- gettoni e casa (ECO-018, 087)
    async def gettoni(self, user_id: int) -> int:
        return int(await self._pool.fetchval("SELECT saldo FROM economia_gettoni WHERE user_id = $1", user_id) or 0)

    @staticmethod
    async def _da_gettoni(conn: asyncpg.Connection, user_id: int, n: int) -> None:
        if n > 0:
            await conn.execute(
                "INSERT INTO economia_gettoni (user_id, saldo) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET saldo = economia_gettoni.saldo + $2",
                user_id, n,
            )

    async def casa(self, user_id: int) -> set[str]:
        return {r["mobile"] for r in await self._pool.fetch("SELECT mobile FROM economia_casa WHERE user_id = $1", user_id)}

    async def compra_mobile(self, user_id: int, mobile: str) -> str:
        """«ok», «gia» o «poche» (gettoni). Mobile e addebito insieme; il mobile si prende con INSERT ... DO NOTHING."""
        if mobile not in MOBILI:
            raise ValueError("Mobile sconosciuto.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if await conn.fetchval("INSERT INTO economia_casa (user_id, mobile) VALUES ($1, $2) ON CONFLICT DO NOTHING RETURNING 1", user_id, mobile) is None:
                    return "gia"
                ok = await conn.fetchval(
                    "UPDATE economia_gettoni SET saldo = saldo - $2 WHERE user_id = $1 AND saldo >= $2 RETURNING 1", user_id, MOBILI[mobile][0]
                )
                if ok is None:
                    await conn.execute("DELETE FROM economia_casa WHERE user_id = $1 AND mobile = $2", user_id, mobile)
                    return "poche"
                return "ok"

    # ---------------------------------------------------------------- vacanza (ECO-027)
    async def compra_vacanza(self, guild_id: int, user_id: int, giorni: int) -> str:
        """La serie del premio giornaliero resta ferma per `giorni`. «ok», «attiva», «nessuna_serie» o «poche»."""
        if not 1 <= giorni <= VACANZA_GIORNI_MAX:
            raise ValueError("Giorni non validi.")
        costo = COSTO_VACANZA_GIORNO * giorni
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                r = await conn.fetchrow(
                    "SELECT serie, vacanza_fino > now() AS attiva FROM progress_serie WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id
                )
                if r is None or r["serie"] <= 0:
                    return "nessuna_serie"
                if r["attiva"]:
                    return "attiva"
                if not await spend_coins_in(conn, guild_id, user_id, costo, "vacanza"):
                    return "poche"
                await deposit_in(conn, guild_id, costo, "vacanza")
                await conn.execute(
                    "UPDATE progress_serie SET vacanza_da = now(), vacanza_fino = now() + make_interval(days => $3) WHERE guild_id = $1 AND user_id = $2",
                    guild_id, user_id, giorni,
                )
                return "ok"

    # ---------------------------------------------------------------- diretta (ECO-045)
    async def diretta(self, guild_id: int, user_id: int, oggi: date) -> tuple[int, int] | None:
        """Una volta al giorno: (serie, monete). None se oggi è già fatta."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("INSERT INTO economia_diretta (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, user_id)
                r = await conn.fetchrow("SELECT serie, ultimo FROM economia_diretta WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id)
                nuova = serie_diretta(r["serie"], r["ultimo"], oggi)
                if nuova is None:
                    return None
                await conn.execute("UPDATE economia_diretta SET serie = $3, ultimo = $4 WHERE guild_id = $1 AND user_id = $2", guild_id, user_id, nuova, oggi)
                monete = paga_diretta(nuova)
                await add_coins_in(conn, guild_id, user_id, monete, motivo="diretta")
                return nuova, monete

    # ---------------------------------------------------------------- fattoria (ECO-146)
    async def orto(self, guild_id: int, user_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT posto, coltura, piantato_at FROM economia_fattoria WHERE guild_id = $1 AND user_id = $2 ORDER BY posto", guild_id, user_id
        )

    async def pianta(self, guild_id: int, user_id: int, posto: int, coltura: str) -> str:
        """«ok», «occupato» o «poche». Il seme va alla cassa."""
        if coltura not in COLTURE or not 1 <= posto <= POSTI_FATTORIA:
            raise ValueError("Coltura o posto non validi.")
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    if await conn.fetchval(
                        "INSERT INTO economia_fattoria (guild_id, user_id, posto, coltura) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING RETURNING 1",
                        guild_id, user_id, posto, coltura,
                    ) is None:
                        return "occupato"
                    costo = COLTURE[coltura][0]
                    if not await spend_coins_in(conn, guild_id, user_id, costo, "fattoria"):
                        raise _Annulla("poche")  # annulla anche il posto occupato
                    await deposit_in(conn, guild_id, costo, "fattoria")
                    return "ok"
        except _Annulla as e:
            return e.esito

    async def raccogli(self, guild_id: int, user_id: int) -> tuple[list[str], int]:
        """Raccoglie e paga tutto ciò che è maturo: righe cancellate con DELETE ... RETURNING, una volta sola."""
        pronti = " OR ".join(f"(coltura = '{nome}' AND piantato_at <= now() - interval '{ore} hours')" for nome, (_, ore, _) in COLTURE.items())  # costanti del codice
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    f"DELETE FROM economia_fattoria WHERE guild_id = $1 AND user_id = $2 AND ({pronti}) RETURNING coltura", guild_id, user_id
                )
                colture = [r["coltura"] for r in righe]
                totale = sum(COLTURE[c][2] for c in colture)
                if totale:
                    await add_coins_in(conn, guild_id, user_id, totale, motivo="fattoria")
                return colture, totale

    # ---------------------------------------------------------------- personaggi (ECO-142) e avventure (ECO-147)
    async def missione(self, guild_id: int, user_id: int, npc: str, oggi: date, giusta: bool, monete: int) -> str:
        """Un tentativo al giorno per personaggio, giusto o sbagliato. «ok» (regalo: monete e un gettone), «sbagliata» o «gia»."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                preso = await conn.fetchval(
                    "INSERT INTO economia_personaggi (guild_id, user_id, npc, giorno) VALUES ($1, $2, $3, $4) ON CONFLICT (guild_id, user_id, npc) "
                    "DO UPDATE SET giorno = EXCLUDED.giorno WHERE economia_personaggi.giorno < EXCLUDED.giorno RETURNING 1", guild_id, user_id, npc, oggi,
                )
                if preso is None:
                    return "gia"
                if not giusta:
                    return "sbagliata"
                await add_coins_in(conn, guild_id, user_id, monete, classifica=False, motivo="personaggio")
                await self._da_gettoni(conn, user_id, 1)
                return "ok"

    async def finale_avventura(self, guild_id: int, user_id: int, monete: int, gettoni: int, pausa_s: int) -> bool:
        """Premio del finale, una volta ogni `pausa_s`. False se la pausa non è finita."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if await conn.fetchval(
                    "INSERT INTO economia_pause (guild_id, user_id, chiave, ultima_at) VALUES ($1, $2, 'avventura_storia', now()) "
                    "ON CONFLICT (guild_id, user_id, chiave) DO UPDATE SET ultima_at = now() "
                    "WHERE economia_pause.ultima_at <= now() - make_interval(secs => $3) RETURNING 1", guild_id, user_id, float(pausa_s),
                ) is None:
                    return False
                if monete:
                    await add_coins_in(conn, guild_id, user_id, monete, classifica=False, motivo="avventura")
                await self._da_gettoni(conn, user_id, gettoni)
                return True

    # ---------------------------------------------------------------- borsa (ECO-084, 085)
    async def prezzi(self) -> dict[str, int]:
        """Prezzi di adesso, uguali per tutti. Si fanno avanzare di un passo all'ora (al massimo 24) e poi scattano gli ordini."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('borsa', 0))")
                for s, base in SIMBOLI.items():
                    await conn.execute("INSERT INTO economia_borsa_prezzi (simbolo, prezzo) VALUES ($1, $2) ON CONFLICT DO NOTHING", s, base)
                righe = await conn.fetch("SELECT simbolo, prezzo, EXTRACT(EPOCH FROM now() - aggiornato_at) AS s FROM economia_borsa_prezzi")
                mossi = False
                for r in righe:
                    passi = int(r["s"] // PASSO_BORSA_S)
                    if passi > 0 and r["simbolo"] in SIMBOLI:
                        mossi = True
                        await conn.execute(
                            "UPDATE economia_borsa_prezzi SET prezzo = $2, aggiornato_at = now() WHERE simbolo = $1",
                            r["simbolo"], prezzo_dopo(r["prezzo"], SIMBOLI[r["simbolo"]], passi, RNG),
                        )
                prezzi = {r["simbolo"]: r["prezzo"] for r in await conn.fetch("SELECT simbolo, prezzo FROM economia_borsa_prezzi")}
                if mossi:
                    await self._esegui_ordini(conn, prezzi)
                return {s: p for s, p in prezzi.items() if s in SIMBOLI}

    @staticmethod
    async def _compra_in(conn, guild_id: int, user_id: int, simbolo: str, quote: int, prezzo: int) -> str:
        posseduti = await conn.fetchval("SELECT quote FROM economia_borsa WHERE guild_id = $1 AND user_id = $2 AND simbolo = $3 FOR UPDATE", guild_id, user_id, simbolo) or 0
        if posseduti + quote > MAX_QUOTE_PER_TITOLO:
            return "troppe"
        costo = costo_con_commissione(prezzo, quote)
        if not await spend_coins_in(conn, guild_id, user_id, costo, "borsa"):
            return "poche"
        await deposit_in(conn, guild_id, costo - prezzo * quote, "borsa") if costo > prezzo * quote else None
        await conn.execute(
            "INSERT INTO economia_borsa (guild_id, user_id, simbolo, quote) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (guild_id, user_id, simbolo) DO UPDATE SET quote = economia_borsa.quote + $4", guild_id, user_id, simbolo, quote,
        )
        return "ok"

    @staticmethod
    async def _vendi_in(conn, guild_id: int, user_id: int, simbolo: str, quote: int, prezzo: int) -> str:
        ok = await conn.fetchval(
            "UPDATE economia_borsa SET quote = quote - $4 WHERE guild_id = $1 AND user_id = $2 AND simbolo = $3 AND quote >= $4 RETURNING 1",
            guild_id, user_id, simbolo, quote,
        )
        if ok is None:
            return "non_hai"
        await conn.execute("DELETE FROM economia_borsa WHERE guild_id = $1 AND user_id = $2 AND simbolo = $3 AND quote = 0", guild_id, user_id, simbolo)
        await add_coins_in(conn, guild_id, user_id, ricavo_con_commissione(prezzo, quote), classifica=False, motivo="borsa")
        return "ok"

    async def scambia(self, guild_id: int, user_id: int, simbolo: str, quote: int, lato: str) -> tuple[str, int]:
        """Compra o vende al prezzo di adesso (3% di commissione, alla cassa se compri). («ok»|«poche»|«troppe»|«non_hai», prezzo)."""
        if simbolo not in SIMBOLI or lato not in ("compra", "vendi") or not 1 <= quote <= 100:
            raise ValueError("Titolo, lato o quantità non validi.")
        prezzo = (await self.prezzi())[simbolo]
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                f = self._compra_in if lato == "compra" else self._vendi_in
                esito = await f(conn, guild_id, user_id, simbolo, quote, prezzo)
                return esito, prezzo

    async def portafoglio(self, guild_id: int, user_id: int) -> dict[str, int]:
        return {r["simbolo"]: r["quote"] for r in await self._pool.fetch(
            "SELECT simbolo, quote FROM economia_borsa WHERE guild_id = $1 AND user_id = $2 AND quote > 0", guild_id, user_id)}

    async def ordine(self, guild_id: int, user_id: int, simbolo: str, lato: str, quote: int, soglia: int) -> str:
        """Ordine a soglia (massimo 5): scatta alla prima variazione dei prezzi che lo rende vero. «ok», «troppi»."""
        if simbolo not in SIMBOLI or lato not in ("compra", "vendi") or not 1 <= quote <= 100 or soglia < 1:
            raise ValueError("Ordine non valido.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"ordini:{guild_id}:{user_id}")
                if await conn.fetchval("SELECT count(*) FROM economia_borsa_ordini WHERE guild_id = $1 AND user_id = $2", guild_id, user_id) >= MAX_ORDINI:
                    return "troppi"
                await conn.execute(
                    "INSERT INTO economia_borsa_ordini (guild_id, user_id, simbolo, lato, quote, soglia) VALUES ($1, $2, $3, $4, $5, $6)",
                    guild_id, user_id, simbolo, lato, quote, soglia,
                )
                return "ok"

    async def ordini(self, guild_id: int, user_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT id, simbolo, lato, quote, soglia FROM economia_borsa_ordini WHERE guild_id = $1 AND user_id = $2 ORDER BY id", guild_id, user_id
        )

    async def togli_ordine(self, guild_id: int, user_id: int, ordine_id: int) -> bool:
        r = await self._pool.execute("DELETE FROM economia_borsa_ordini WHERE id = $1 AND guild_id = $2 AND user_id = $3", ordine_id, guild_id, user_id)
        return r.endswith(" 1")

    async def _esegui_ordini(self, conn, prezzi: dict[str, int]) -> int:
        """Gli ordini veri si eseguono in ordine di arrivo; riusciti o falliti (pochi soldi, troppi titoli) escono dalla lista."""
        fatti = 0
        for o in await conn.fetch("SELECT id, guild_id, user_id, simbolo, lato, quote, soglia FROM economia_borsa_ordini ORDER BY id"):
            p = prezzi.get(o["simbolo"])
            if p is None or not ordine_scatta(o["lato"], p, o["soglia"]):
                continue
            await conn.execute("DELETE FROM economia_borsa_ordini WHERE id = $1", o["id"])
            f = self._compra_in if o["lato"] == "compra" else self._vendi_in
            if await f(conn, o["guild_id"], o["user_id"], o["simbolo"], o["quote"], p) == "ok":
                fatti += 1
        return fatti

    # ---------------------------------------------------------------- vendita automatica (ECO-083)
    async def autovendita(self, guild_id: int, user_id: int, item_id: int, soglia: int) -> str:
        """«ok» o «troppe» (massimo 5 oggetti), «non_c_e» se l'oggetto non è di questo server."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"autov:{guild_id}:{user_id}")
                if not await conn.fetchval("SELECT 1 FROM shop_items WHERE id = $1 AND guild_id = $2", item_id, guild_id):
                    return "non_c_e"
                if await conn.fetchval(
                    "SELECT count(*) FROM economia_autovendita WHERE guild_id = $1 AND user_id = $2 AND item_id <> $3", guild_id, user_id, item_id
                ) >= MAX_AUTOVENDITE:
                    return "troppe"
                await conn.execute(
                    "INSERT INTO economia_autovendita (guild_id, user_id, item_id, soglia) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET soglia = EXCLUDED.soglia", guild_id, user_id, item_id, soglia,
                )
                return "ok"

    async def togli_autovendita(self, guild_id: int, user_id: int, item_id: int) -> bool:
        r = await self._pool.execute("DELETE FROM economia_autovendita WHERE guild_id = $1 AND user_id = $2 AND item_id = $3", guild_id, user_id, item_id)
        return r.endswith(" 1")

    async def autovendite(self, guild_id: int, user_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT a.item_id, a.soglia, s.name FROM economia_autovendita a JOIN shop_items s ON s.id = a.item_id WHERE a.guild_id = $1 AND a.user_id = $2 ORDER BY a.item_id",
            guild_id, user_id,
        )

    async def autovendite_del_giorno(self, tasso_per_server) -> int:
        """Per ogni server: le regole con soglia <= cambio di oggi vendono tutti i pezzi posseduti (una vendita per pezzo)."""
        from core.repositories.inventario_repo import Esito, InventarioRepository

        inv = InventarioRepository(pool_provider=self._pool_provider)
        venduti = 0
        for g in [r["guild_id"] for r in await self._pool.fetch("SELECT DISTINCT guild_id FROM economia_autovendita")]:
            tasso = tasso_per_server(g)
            for r in await self._pool.fetch("SELECT user_id, item_id FROM economia_autovendita WHERE guild_id = $1 AND soglia <= $2", g, tasso):
                for _ in range(100):
                    if (await inv.vendi(g, r["user_id"], r["item_id"])).esito is not Esito.FATTO:
                        break
                    venduti += 1
        return venduti

    # ---------------------------------------------------------------- eventi in chat e bonus a tempo (ECO-054, 056, 144, 145)
    async def crea_evento(self, guild_id: int, tipo: str, codice: str | None, monete: int, percento: int, minuti: int, scade_min: int, autore: int) -> int:
        return await self._pool.fetchval(
            "INSERT INTO economia_chat_eventi (guild_id, tipo, codice, monete, percento, minuti, scade_at, creato_da) "
            "VALUES ($1, $2, $3, $4, $5, $6, now() + make_interval(mins => $7), $8) RETURNING id",
            guild_id, tipo, codice, monete, percento, minuti, scade_min, autore,
        )

    async def prendi_evento(self, guild_id: int, evento_id: int, user_id: int, codice: str | None = None) -> tuple[str, dict | None]:
        """Il primo che arriva (e, per il codice, scrive quello giusto) prende il premio. («ok»|«sbagliato»|«preso»|«scaduto», dati)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                e = await conn.fetchrow(
                    "UPDATE economia_chat_eventi SET preso_da = $3 WHERE id = $1 AND guild_id = $2 AND preso_da IS NULL AND scade_at > now() "
                    "AND (tipo <> 'codice' OR lower(codice) = lower($4)) RETURNING tipo, monete, percento, minuti",
                    evento_id, guild_id, user_id, (codice or "").strip(),
                )
                if e is None:
                    stato = await conn.fetchrow("SELECT preso_da IS NOT NULL AS preso, scade_at <= now() AS scaduto FROM economia_chat_eventi WHERE id = $1 AND guild_id = $2", evento_id, guild_id)
                    if stato is None or stato["scaduto"]:
                        return "scaduto", None
                    return ("preso" if stato["preso"] else "sbagliato"), None
                if e["monete"]:
                    await add_coins_in(conn, guild_id, user_id, e["monete"], classifica=False, motivo=f"evento_{e['tipo']}")
                if e["percento"] and e["minuti"]:
                    await self._bonus_in(conn, guild_id, user_id, e["percento"], e["minuti"])
                return "ok", dict(e)

    @staticmethod
    async def _bonus_in(conn, guild_id: int, user_id: int, percento: int, minuti: int) -> None:
        await conn.execute(
            "INSERT INTO economia_bonus_tempo (guild_id, user_id, percento, fino) VALUES ($1, $2, $3, now() + make_interval(mins => $4)) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET percento = EXCLUDED.percento, fino = EXCLUDED.fino", guild_id, user_id, percento, minuti,
        )

    async def bonus_server(self, guild_id: int, percento: int, minuti: int) -> None:
        async with self._pool.acquire() as conn:
            await self._bonus_in(conn, guild_id, TUTTO_IL_SERVER, percento, minuti)

    async def bonus_percento(self, guild_id: int, user_id: int) -> int:
        """Bonus % a lavoro e premio in questo momento: il tuo e quello del server insieme, al massimo 100."""
        tot = await self._pool.fetchval(
            "SELECT COALESCE(sum(percento), 0) FROM economia_bonus_tempo WHERE guild_id = $1 AND user_id IN ($2, $3) AND fino > now()",
            guild_id, user_id, TUTTO_IL_SERVER,
        )
        return min(100, int(tot))

    async def imposta_eventi(self, guild_id: int, canale_id: int, attivo: bool) -> None:
        await self._pool.execute(
            "INSERT INTO economia_eventi_conf (guild_id, canale_id, attivo) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id) DO UPDATE SET canale_id = EXCLUDED.canale_id, attivo = EXCLUDED.attivo", guild_id, canale_id, attivo,
        )

    async def eventi_pronti(self, ore_di_pausa: int = 6, limite: int = 50) -> list[asyncpg.Record]:
        """Server con gli eventi accesi e nessun evento nelle ultime ore; chi li prende li segna subito (una sola riga alla volta)."""
        return await self._pool.fetch(
            "UPDATE economia_eventi_conf SET ultimo_at = now() WHERE guild_id IN (SELECT guild_id FROM economia_eventi_conf WHERE attivo AND "
            "(ultimo_at IS NULL OR ultimo_at < now() - make_interval(hours => $1)) ORDER BY guild_id LIMIT $2 FOR UPDATE SKIP LOCKED) "
            "RETURNING guild_id, canale_id", ore_di_pausa, limite,
        )

    async def pulisci(self) -> None:
        await self._pool.execute("DELETE FROM economia_chat_eventi WHERE scade_at < now() - interval '1 day'")
        await self._pool.execute("DELETE FROM economia_bonus_tempo WHERE fino < now() - interval '1 day'")


class _Annulla(Exception):
    def __init__(self, esito: str) -> None:
        self.esito = esito


def _get_pool():
    from core.database import db

    return db.pool


mondo_repo = MondoRepository(pool_provider=_get_pool)
