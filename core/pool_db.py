"""
core/pool_db.py
===============
Il pool di PostgreSQL con due difese contro l'attesa infinita:
1) ogni richiesta di connessione ha un tempo massimo (10 s, 15 s per gli eventi): se il pool è
   pieno si fallisce con `asyncio.TimeoutError` invece di restare in coda per sempre;
2) due corsie: gli eventi del bot (messaggi, ingressi...) non possono occupare TUTTE le connessioni,
   ne restano sempre alcune libere per i comandi e per i giri periodici. Durante un raid i comandi
   di moderazione continuano a rispondere. La corsia si sceglie con `corsia_db` (la imposta
   `iYokaiBot._run_event`).
Funzioni coperte: consiglio 25/11/2026, critico 9 (blocco C)
"""

from __future__ import annotations

import asyncio
import contextvars
import time

import asyncpg

TIMEOUT_COMANDI_SECONDI = 10.0
TIMEOUT_EVENTI_SECONDI = 15.0
CORSIA_EVENTI = "eventi"
CORSIA_COMANDI = "comandi"

# Corsia della richiesta in corso: ogni task di un evento la porta con sé (asyncio copia il contesto).
corsia_db: contextvars.ContextVar[str] = contextvars.ContextVar("corsia_db", default=CORSIA_COMANDI)


def connessioni_per_eventi(max_size: int) -> int:
    """Quante connessioni al massimo possono servire gli eventi insieme: il resto (almeno 2) è dei comandi."""
    riserva = max(2, max_size // 3)
    return max(1, max_size - riserva)


class PoolConCorsie(asyncpg.Pool):
    """`asyncpg.Pool` con attesa massima e corsia per gli eventi."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._semaforo_eventi = asyncio.Semaphore(connessioni_per_eventi(self._maxsize))
        self._connessioni_eventi: set[int] = set()  # id delle connessioni date alla corsia eventi

    async def _acquire(self, timeout):
        eventi = corsia_db.get() == CORSIA_EVENTI
        if timeout is None:
            timeout = TIMEOUT_EVENTI_SECONDI if eventi else TIMEOUT_COMANDI_SECONDI
        if not eventi:
            return await super()._acquire(timeout)
        scadenza = time.monotonic() + timeout
        await asyncio.wait_for(self._semaforo_eventi.acquire(), timeout)
        try:
            con = await super()._acquire(max(0.01, scadenza - time.monotonic()))
        except BaseException:
            self._semaforo_eventi.release()
            raise
        self._connessioni_eventi.add(id(con))
        return con

    async def release(self, connection, *, timeout=None):
        era_degli_eventi = id(connection) in self._connessioni_eventi
        self._connessioni_eventi.discard(id(connection))
        try:
            await super().release(connection, timeout=timeout)
        finally:
            if era_degli_eventi:
                self._semaforo_eventi.release()
