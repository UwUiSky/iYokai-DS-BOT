"""
core/giro_periodico.py
======================
Classe comune per tutti i lavori periodici del bot (al posto di `tasks.loop`).
Un giro che va in errore non muore più: l'errore si scrive nel log, si aspetta una pausa
sempre più lunga (5 s, 10 s, 20 s... fino a 15 minuti) e si riprova. L'ultimo giro riuscito
sta nel database: dopo un riavvio i lavori lunghi non ripartono tutti insieme.
Con più processi sullo stesso database gira solo il «leader» (lock `pg_try_advisory_lock`).
Funzioni coperte: consiglio 25/11/2026, critico 10 (blocco C).
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Callable

import asyncpg
from discord.ext import tasks
from discord.utils import MISSING

logger = logging.getLogger(__name__)

PAUSA_BASE_SECONDI = 5
PAUSA_MASSIMA_SECONDI = 900
# Sotto questo intervallo il giro riparte sempre subito: non vale la pena aspettare.
SOGLIA_RIPRESA_SECONDI = 300
# Il database si aggiorna al massimo una volta al minuto per giro (alcuni girano ogni 5 secondi).
SALVATAGGIO_MINIMO_SECONDI = 60
# Dopo quanti errori di fila si avvisa chi ascolta (l'owner, vedi core/avvisi_owner.py).
ERRORI_PER_AVVISO = 3
# Chiave del lock di leadership (uguale in ogni processo).
CHIAVE_LEADERSHIP = 0x1409A1


def pausa_dopo_errori(errori_consecutivi: int) -> float:
    """Pausa in secondi dopo N errori di fila: raddoppia ogni volta, con un tetto."""
    if errori_consecutivi <= 0:
        return 0.0
    esponente = min(errori_consecutivi - 1, 20)
    return float(min(PAUSA_MASSIMA_SECONDI, PAUSA_BASE_SECONDI * 2**esponente))


# Tutti i giri creati, per /salute e per i test (chiave: nome).
GIRI: dict[str, "GiroPeriodico"] = {}

# Chi vuole sapere quando un giro cade o torna.
ascoltatori_caduta: list[Callable[[str, int, str], None]] = []
ascoltatori_ripresa: list[Callable[[str], None]] = []


class Leadership:
    """Un solo processo alla volta fa girare i giri: chi tiene il lock del database.

    Il lock sta su una connessione dedicata. Se il database non risponde non si può sapere:
    si tiene l'ultimo stato noto (all'inizio: leader), così un guasto non spegne i lavori.
    """

    def __init__(self) -> None:
        self._conn: asyncpg.Connection | None = None
        self._leader = True

    async def sono_leader(self, dsn: str | None) -> bool:
        if not dsn:
            return True
        if self._conn is not None and not self._conn.is_closed():
            return self._leader
        try:
            conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=10)
            self._leader = bool(await conn.fetchval("SELECT pg_try_advisory_lock($1)", CHIAVE_LEADERSHIP))
            self._conn = conn
        except Exception:
            logger.warning("Lock di leadership non verificabile: tengo l'ultimo stato (leader=%s).", self._leader)
            self._conn = None
        return self._leader

    async def rilascia(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None and not conn.is_closed():
            try:
                await asyncio.wait_for(conn.close(), timeout=5)
            except Exception:
                conn.terminate()
        self._leader = True


leadership = Leadership()


def _dsn_e_pool() -> tuple[str | None, Any]:
    """DSN del database e pool, se aperti. Import tardivo: il modulo non dipende da database.py."""
    from core.config import config
    from core.database import db

    pool = db._pool
    return (config.DATABASE_URL if pool is not None else None), pool


class GiroPeriodico(tasks.Loop):
    """Un `tasks.Loop` che non muore: errori contati, pause crescenti, stato nel database."""

    def __init__(self, coro, *, subito: bool = False, **kw) -> None:
        self._originale = coro
        self._subito = subito
        self.errori_consecutivi = 0
        self.ultimo_ok: datetime | None = None
        self.ultimo_errore: str | None = None
        self.ultimo_salvataggio: float | None = None
        self._avvisato = False
        nome_task = kw.pop("name", None)
        self.nome = f"{coro.__module__}.{coro.__qualname__}"[:200]
        super().__init__(self._protetto_per(coro), name=nome_task or f"giro: {self.nome}", **kw)
        GIRI[self.nome] = self

    def _protetto_per(self, coro):
        giro = self

        async def _protetto(*args, **kwargs):
            if not await giro._sono_leader():
                return
            try:
                await coro(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await giro._dopo_errore(exc)
            else:
                await giro._dopo_successo()

        _protetto.__name__ = getattr(coro, "__name__", "giro")
        _protetto.__qualname__ = getattr(coro, "__qualname__", "giro")
        _protetto.__module__ = getattr(coro, "__module__", __name__)
        return _protetto

    async def _sono_leader(self) -> bool:
        dsn, _ = _dsn_e_pool()
        return await leadership.sono_leader(dsn)

    async def _dopo_successo(self) -> None:
        era_caduto = self._avvisato
        self.errori_consecutivi = 0
        self.ultimo_errore = None
        self._avvisato = False
        self.ultimo_ok = datetime.now(timezone.utc)
        await self._salva()
        if era_caduto:
            for ascolta in ascoltatori_ripresa:
                _chiama(ascolta, self.nome)

    async def _dopo_errore(self, exc: Exception) -> None:
        self.errori_consecutivi += 1
        self.ultimo_errore = f"{type(exc).__name__}: {exc}"[:500]
        logger.error(
            "Giro %s in errore (%d di fila), riprovo tra %.0f s.",
            self.nome, self.errori_consecutivi, pausa_dopo_errori(self.errori_consecutivi),
            exc_info=exc,
        )
        await self._salva()
        if self.errori_consecutivi >= ERRORI_PER_AVVISO and not self._avvisato:
            self._avvisato = True
            for ascolta in ascoltatori_caduta:
                _chiama(ascolta, self.nome, self.errori_consecutivi, self.ultimo_errore)
        await asyncio.sleep(pausa_dopo_errori(self.errori_consecutivi))

    async def _salva(self) -> None:
        """Scrive lo stato nel database: dopo un successo al massimo una volta al minuto, dopo un errore sempre."""
        adesso = asyncio.get_running_loop().time()
        if (
            self.errori_consecutivi == 0
            and self.ultimo_salvataggio is not None
            and adesso - self.ultimo_salvataggio < SALVATAGGIO_MINIMO_SECONDI
        ):
            return
        _, pool = _dsn_e_pool()
        if pool is None:
            return
        self.ultimo_salvataggio = adesso
        try:
            await asyncio.wait_for(
                pool.execute(
                    """
                    INSERT INTO giri_periodici (nome, ultimo_giro_ok, ultimo_errore, errori_consecutivi, testo_errore)
                    VALUES ($1, $2, CASE WHEN $3::int > 0 THEN now() END, $3::int, $4)
                    ON CONFLICT (nome) DO UPDATE SET
                        ultimo_giro_ok = COALESCE(EXCLUDED.ultimo_giro_ok, giri_periodici.ultimo_giro_ok),
                        ultimo_errore = CASE WHEN $3::int > 0 THEN now() ELSE giri_periodici.ultimo_errore END,
                        errori_consecutivi = EXCLUDED.errori_consecutivi,
                        testo_errore = EXCLUDED.testo_errore
                    """,
                    self.nome,
                    self.ultimo_ok if self.errori_consecutivi == 0 else None,
                    self.errori_consecutivi,
                    self.ultimo_errore,
                ),
                timeout=10,
            )
        except Exception:
            logger.warning("Stato del giro %s non salvato (database non raggiungibile).", self.nome)

    def _intervallo_secondi(self) -> float:
        return (self._seconds or 0) + (self._minutes or 0) * 60 + (self._hours or 0) * 3600

    async def _attesa_iniziale(self) -> None:
        """Dopo un riavvio: aspetta il resto dell'intervallo se l'ultimo giro è recente, più un piccolo scarto."""
        intervallo = self._intervallo_secondi()
        if self._subito or intervallo < 30:
            return
        attesa = random.uniform(0, min(30.0, intervallo * 0.1))
        if intervallo >= SOGLIA_RIPRESA_SECONDI:
            _, pool = _dsn_e_pool()
            if pool is not None:
                try:
                    ultimo = await asyncio.wait_for(
                        pool.fetchval("SELECT ultimo_giro_ok FROM giri_periodici WHERE nome = $1", self.nome),
                        timeout=10,
                    )
                except Exception:
                    ultimo = None
                if ultimo is not None:
                    trascorso = (datetime.now(timezone.utc) - ultimo).total_seconds()
                    attesa += max(0.0, intervallo - trascorso)
        if attesa > 0:
            await asyncio.sleep(attesa)

    async def _call_loop_function(self, name: str, *args: Any, **kwargs: Any) -> None:
        await super()._call_loop_function(name, *args, **kwargs)
        if name == "before_loop":
            await self._attesa_iniziale()

    def __get__(self, obj, objtype):
        """Un cog crea una copia del giro per ogni sua istanza (come fa `tasks.Loop`)."""
        if obj is None:
            return self
        copia = GiroPeriodico(
            self._originale, subito=self._subito, seconds=self._seconds, hours=self._hours,
            minutes=self._minutes, time=self._time, count=self.count, reconnect=self.reconnect,
            name=self._name,
        )
        copia._injected = obj
        copia._before_loop = self._before_loop
        copia._after_loop = self._after_loop
        copia._error = self._error
        setattr(obj, self._originale.__name__, copia)
        return copia

    def stato(self) -> dict[str, Any]:
        """Stato leggibile, per /salute."""
        return {
            "nome": self.nome,
            "vivo": self.is_running(),
            "errori_consecutivi": self.errori_consecutivi,
            "ultimo_ok": self.ultimo_ok,
            "ultimo_errore": self.ultimo_errore,
            "intervallo_secondi": self._intervallo_secondi(),
        }


def _chiama(funzione: Callable, *args) -> None:
    try:
        funzione(*args)
    except Exception:
        logger.exception("Ascoltatore dei giri in errore")


def giro_periodico(
    *, seconds: float = MISSING, minutes: float = MISSING, hours: float = MISSING,
    time=MISSING, count: int | None = None, reconnect: bool = True,
    name: str | None = None, subito: bool = False,
):
    """Decoratore al posto di `tasks.loop`: stessi parametri, più `subito=True` (niente attesa dopo il riavvio)."""

    def decoratore(funzione):
        return GiroPeriodico(
            funzione, subito=subito, seconds=seconds, minutes=minutes, hours=hours,
            time=time, count=count, reconnect=reconnect, name=name,
        )

    return decoratore


def stato_giri() -> list[dict[str, Any]]:
    """Stato di tutti i giri conosciuti (vivi o no)."""
    return [g.stato() for g in GIRI.values()]


def giri_in_difficolta() -> list[str]:
    """Nomi dei giri avviati che si sono fermati o che sbagliano da più volte di fila."""
    nomi: list[str] = []
    for giro in GIRI.values():
        if giro._task is None:
            continue  # mai avviato: non è un guasto
        if not giro.is_running() or giro.errori_consecutivi >= ERRORI_PER_AVVISO:
            nomi.append(giro.nome)
    return nomi
