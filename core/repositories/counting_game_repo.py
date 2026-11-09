"""
core/repositories/counting_game_repo.py
=======================================
Gioco del conteggio: fino a 10 canali per server dove si conta a turno 1, 2, 3... (anche in binario, romani o lettere).
Ogni numero è giudicato sotto il blocco della riga del canale, così due numeri arrivati insieme non passano entrambi.
Punteggi per membro, blocchi a tempo, traguardi e avvisi. Tabelle: migrazioni 0552 e 0553.
Funzioni coperte: SPEC §23.16 (NF-40), catalogo UTL-186, 187, 188, 189, 190, 192
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import asyncpg

from core.bounded_cache import BoundedCache
from core.coin_games_logic import valuta_conteggio
from core.conteggio_logic import FILTRI, MAX_AVVISI_PER_UTENTE, MAX_CANALI, MAX_TRAGUARDI_PER_CANALE, MODI, Traguardo

# Quanto resta in memoria l'elenco dei canali: lo chiede ogni messaggio del server.
SECONDI_DI_CACHE = 60
NON_CAMBIA = object()

class TroppiCanali(Exception):
    """Il server conta già in 10 canali."""


class TroppiTraguardi(Exception):
    """Il canale ha già 25 traguardi."""


class TroppiAvvisi(Exception):
    """Il membro ha già 5 avvisi."""

@dataclass(frozen=True)
class StatoConteggio:
    guild_id: int
    channel_id: int
    modo: str
    filtro: str
    current: int
    last_user_id: int | None
    best: int
    punizione_minuti: int
    ruolo_ultimo: int | None

@dataclass(frozen=True)
class EsitoConteggio:
    corretto: bool
    numero: int  # il numero accettato, o l'ultimo giusto se hai sbagliato
    record: int
    precedente: int | None = None  # chi aveva contato per ultimo prima di questo messaggio
    bloccato_fino: datetime | None = None

@dataclass(frozen=True)
class Punteggio:
    user_id: int
    giusti: int
    sbagliati: int

class CountingGameRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache: BoundedCache[int, tuple[float, dict[int, tuple[str, str]]]] = BoundedCache(max_size=5_000)

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ canali
    async def aggiungi_canale(self, guild_id: int, channel_id: int, modo: str = "decimale", filtro: str = "solo_numero") -> bool:
        """Aggiunge il canale o ne cambia modo e filtro (il conteggio riparte da zero, il record resta).
        True se è nuovo. TroppiCanali se il server è già a 10."""
        if modo not in MODI or filtro not in FILTRI:
            raise ValueError("modo o filtro sconosciuto")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext('conteggio_canali'), $1)", guild_id % 2**31)
                esiste = await conn.fetchval(
                    "SELECT 1 FROM conteggio_canali WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id
                )
                if not esiste and await conn.fetchval("SELECT count(*) FROM conteggio_canali WHERE guild_id = $1", guild_id) >= MAX_CANALI:
                    raise TroppiCanali()
                await conn.execute(
                    """
                    INSERT INTO conteggio_canali (guild_id, channel_id, modo, filtro) VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id, channel_id) DO UPDATE
                        SET modo = EXCLUDED.modo, filtro = EXCLUDED.filtro, current = 0, last_user_id = NULL
                    """,
                    guild_id, channel_id, modo, filtro,
                )
        self._cache.delete(guild_id)
        return not esiste

    async def togli_canale(self, guild_id: int, channel_id: int) -> bool:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                esito = await conn.execute(
                    "DELETE FROM conteggio_canali WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id
                )
                for tabella in ("conteggio_blocchi", "conteggio_traguardi", "conteggio_avvisi", "conteggio_punteggi"):
                    await conn.execute(f"DELETE FROM {tabella} WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id)
        self._cache.delete(guild_id)
        return esito.endswith(" 1")

    async def get(self, guild_id: int, channel_id: int) -> StatoConteggio | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM conteggio_canali WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id
        )
        return StatoConteggio(**dict(row)) if row is not None else None

    async def elenco(self, guild_id: int) -> list[StatoConteggio]:
        righe = await self._pool.fetch("SELECT * FROM conteggio_canali WHERE guild_id = $1 ORDER BY channel_id", guild_id)
        return [StatoConteggio(**dict(r)) for r in righe]

    async def canali(self, guild_id: int) -> dict[int, tuple[str, str]]:
        """channel_id -> (modo, filtro), con una risposta tenuta in memoria per un minuto (solo dopo una lettura riuscita)."""
        voce = self._cache.get(guild_id)
        if voce is not None and time.monotonic() - voce[0] < SECONDI_DI_CACHE:
            return voce[1]
        righe = await self._pool.fetch(
            "SELECT channel_id, modo, filtro FROM conteggio_canali WHERE guild_id = $1", guild_id
        )
        canali = {r["channel_id"]: (r["modo"], r["filtro"]) for r in righe}
        self._cache.set(guild_id, (time.monotonic(), canali))
        return canali

    async def imposta_regole(self, guild_id: int, channel_id: int, *, punizione_minuti=NON_CAMBIA, ruolo_ultimo=NON_CAMBIA) -> bool:
        """Punizione (minuti senza poter contare dopo uno sbaglio) e ruolo di chi ha contato per ultimo."""
        stato = await self.get(guild_id, channel_id)
        if stato is None:
            return False
        minuti = stato.punizione_minuti if punizione_minuti is NON_CAMBIA else punizione_minuti
        ruolo = stato.ruolo_ultimo if ruolo_ultimo is NON_CAMBIA else ruolo_ultimo
        await self._pool.execute(
            "UPDATE conteggio_canali SET punizione_minuti = $3, ruolo_ultimo = $4 WHERE guild_id = $1 AND channel_id = $2",
            guild_id, channel_id, minuti, ruolo,
        )
        return True

    # ------------------------------------------------------------ gioco
    async def blocco_attivo(self, guild_id: int, channel_id: int, user_id: int) -> datetime | None:
        """Fino a quando l'utente non può contare in quel canale, se è bloccato."""
        scade = await self._pool.fetchval(
            "SELECT scade_il FROM conteggio_blocchi WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3",
            guild_id, channel_id, user_id,
        )
        return scade if scade is not None and scade > datetime.now(timezone.utc) else None

    async def register(self, guild_id: int, channel_id: int, user_id: int, numero: int) -> EsitoConteggio | None:
        """
        Giudica un numero scritto nel canale. Giusto (il successivo, da una persona diversa dall'ultima): il conteggio
        avanza. Sbagliato: riparte da zero, e se il canale ha una punizione chi ha sbagliato resta bloccato.
        None se quel server non conta in quel canale.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                riga = await conn.fetchrow(
                    "SELECT current, last_user_id, best, punizione_minuti FROM conteggio_canali "
                    "WHERE guild_id = $1 AND channel_id = $2 FOR UPDATE",
                    guild_id, channel_id,
                )
                if riga is None:
                    return None
                if valuta_conteggio(riga["current"], riga["last_user_id"], user_id, numero):
                    record = max(riga["best"], numero)
                    await conn.execute(
                        "UPDATE conteggio_canali SET current = $3, last_user_id = $4, best = $5 "
                        "WHERE guild_id = $1 AND channel_id = $2",
                        guild_id, channel_id, numero, user_id, record,
                    )
                    await self._punto(conn, guild_id, channel_id, user_id, giusto=True)
                    return EsitoConteggio(True, numero, record, riga["last_user_id"])
                await conn.execute(
                    "UPDATE conteggio_canali SET current = 0, last_user_id = NULL WHERE guild_id = $1 AND channel_id = $2",
                    guild_id, channel_id,
                )
                await self._punto(conn, guild_id, channel_id, user_id, giusto=False)
                fino = None
                if riga["punizione_minuti"]:
                    fino = datetime.now(timezone.utc) + timedelta(minutes=riga["punizione_minuti"])
                    await conn.execute(
                        "INSERT INTO conteggio_blocchi (guild_id, channel_id, user_id, scade_il) VALUES ($1, $2, $3, $4) "
                        "ON CONFLICT (guild_id, channel_id, user_id) DO UPDATE SET scade_il = EXCLUDED.scade_il",
                        guild_id, channel_id, user_id, fino,
                    )
                return EsitoConteggio(False, riga["current"], riga["best"], riga["last_user_id"], fino)

    @staticmethod
    async def _punto(conn, guild_id: int, channel_id: int, user_id: int, *, giusto: bool) -> None:
        await conn.execute(
            f"INSERT INTO conteggio_punteggi (guild_id, channel_id, user_id, {'giusti' if giusto else 'sbagliati'}) "
            "VALUES ($1, $2, $3, 1) ON CONFLICT (guild_id, channel_id, user_id) DO UPDATE "
            f"SET {'giusti' if giusto else 'sbagliati'} = conteggio_punteggi.{'giusti' if giusto else 'sbagliati'} + 1",
            guild_id, channel_id, user_id,
        )

    # ------------------------------------------------------------ classifica
    async def classifica(self, guild_id: int, channel_id: int | None, limite: int, scarto: int = 0) -> list[Punteggio]:
        """Chi ha contato più numeri giusti (in un canale, o in tutto il server)."""
        righe = await self._pool.fetch(
            "SELECT user_id, SUM(giusti)::int AS giusti, SUM(sbagliati)::int AS sbagliati FROM conteggio_punteggi "
            "WHERE guild_id = $1 AND ($2::bigint IS NULL OR channel_id = $2) GROUP BY user_id "
            "ORDER BY giusti DESC, sbagliati, user_id LIMIT $3 OFFSET $4",
            guild_id, channel_id, limite, scarto,
        )
        return [Punteggio(**dict(r)) for r in righe]

    async def conta_giocatori(self, guild_id: int, channel_id: int | None) -> int:
        return await self._pool.fetchval(
            "SELECT count(DISTINCT user_id) FROM conteggio_punteggi WHERE guild_id = $1 AND ($2::bigint IS NULL OR channel_id = $2)",
            guild_id, channel_id,
        )

    # ------------------------------------------------------------ traguardi
    async def aggiungi_traguardo(
        self, guild_id: int, channel_id: int, *, numero: int | None, ogni: int | None, ruolo_id: int | None, messaggio: str | None
    ) -> int:
        """Salva un traguardo e ne dà il numero. TroppiTraguardi se il canale è a 25."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext('conteggio_traguardi'), $1)", guild_id % 2**31)
                if await conn.fetchval(
                    "SELECT count(*) FROM conteggio_traguardi WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id
                ) >= MAX_TRAGUARDI_PER_CANALE:
                    raise TroppiTraguardi()
                return await conn.fetchval(
                    "INSERT INTO conteggio_traguardi (guild_id, channel_id, numero, ogni, ruolo_id, messaggio) "
                    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                    guild_id, channel_id, numero, ogni, ruolo_id, messaggio,
                )

    async def togli_traguardo(self, guild_id: int, traguardo_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM conteggio_traguardi WHERE guild_id = $1 AND id = $2", guild_id, traguardo_id
        )
        return esito.endswith(" 1")

    async def traguardi(self, guild_id: int, channel_id: int) -> list[Traguardo]:
        righe = await self._pool.fetch(
            "SELECT id, numero, ogni, ruolo_id, messaggio FROM conteggio_traguardi "
            "WHERE guild_id = $1 AND channel_id = $2 ORDER BY id",
            guild_id, channel_id,
        )
        return [Traguardo(r["id"], r["numero"], r["ogni"], r["ruolo_id"], r["messaggio"]) for r in righe]

    # ------------------------------------------------------------ avvisi
    async def aggiungi_avviso(self, guild_id: int, channel_id: int, user_id: int, numero: int) -> bool:
        """True se nuovo, False se c'era già. TroppiAvvisi se il membro è a 5 nel server."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext('conteggio_avvisi'), $1)", guild_id % 2**31)
                if await conn.fetchval(
                    "SELECT 1 FROM conteggio_avvisi WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3 AND numero = $4",
                    guild_id, channel_id, user_id, numero,
                ):
                    return False
                if await conn.fetchval(
                    "SELECT count(*) FROM conteggio_avvisi WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                ) >= MAX_AVVISI_PER_UTENTE:
                    raise TroppiAvvisi()
                await conn.execute(
                    "INSERT INTO conteggio_avvisi (guild_id, channel_id, user_id, numero) VALUES ($1, $2, $3, $4)",
                    guild_id, channel_id, user_id, numero,
                )
                return True

    async def togli_avvisi(self, guild_id: int, user_id: int) -> int:
        esito = await self._pool.execute("DELETE FROM conteggio_avvisi WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
        return int(esito.split()[-1])

    async def consuma_avvisi(self, guild_id: int, channel_id: int, numero: int) -> list[int]:
        """Chi voleva un avviso a questo numero. Gli avvisi si cancellano: scattano una volta sola."""
        righe = await self._pool.fetch(
            "DELETE FROM conteggio_avvisi WHERE guild_id = $1 AND channel_id = $2 AND numero = $3 RETURNING user_id",
            guild_id, channel_id, numero,
        )
        return [r["user_id"] for r in righe]

    # ------------------------------------------------------------ importazione
    async def importa_punteggi(self, guild_id: int, channel_id: int, righe: list[tuple[int, int, int]]) -> int:
        """Imposta i punteggi dei membri nel canale (chi c'è già viene sovrascritto)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    "INSERT INTO conteggio_punteggi (guild_id, channel_id, user_id, giusti, sbagliati) VALUES ($1, $2, $3, $4, $5) "
                    "ON CONFLICT (guild_id, channel_id, user_id) DO UPDATE "
                    "SET giusti = EXCLUDED.giusti, sbagliati = EXCLUDED.sbagliati",
                    [(guild_id, channel_id, u, g, s) for u, g, s in righe],
                )
        return len(righe)


def _get_pool():
    from core.database import db

    return db.pool

counting_game_repo = CountingGameRepository(pool_provider=_get_pool)
