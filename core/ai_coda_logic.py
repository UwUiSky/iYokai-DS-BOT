"""
core/ai_coda_logic.py
=====================
Coda delle richieste AI: al più `posti` chiamate ai fornitori insieme, le
altre aspettano in fila (al più `max_attesa` in tutto e `max_per_server` per
server, così un server non riempie la fila agli altri) e, se l'attesa supera
`timeout` secondi, rinunciano. Logica pura, senza rete.
Funzioni coperte: SPEC §25.22 (AI-R-022)
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager

POSTI = 4
MAX_ATTESA = 40
MAX_PER_SERVER = 8
TIMEOUT_SECONDI = 25.0


class CodaPiena(Exception):
    """La fila è piena (o il server ha già troppe richieste in fila) o l'attesa è finita."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo  # "coda_piena" | "coda_scaduta"


class CodaAI:
    def __init__(self, posti: int = POSTI, max_attesa: int = MAX_ATTESA, max_per_server: int = MAX_PER_SERVER,
                 timeout: float = TIMEOUT_SECONDI) -> None:
        self._sem = asyncio.Semaphore(posti)
        self.max_attesa = max_attesa
        self.max_per_server = max_per_server
        self.timeout = timeout
        self.in_attesa = 0
        self._per_server: dict[int, int] = defaultdict(int)

    @asynccontextmanager
    async def posto(self, guild_id: int):
        """Tiene un posto per la durata del blocco. Solleva `CodaPiena` se non c'è posto in fila."""
        if not self._sem.locked():
            await self._sem.acquire()
        else:
            if self.in_attesa >= self.max_attesa or self._per_server[guild_id] >= self.max_per_server:
                raise CodaPiena("coda_piena")
            self.in_attesa += 1
            self._per_server[guild_id] += 1
            try:
                await asyncio.wait_for(self._sem.acquire(), self.timeout)
            except asyncio.TimeoutError:
                raise CodaPiena("coda_scaduta") from None
            finally:
                self.in_attesa -= 1
                self._per_server[guild_id] -= 1
                if self._per_server[guild_id] <= 0:
                    del self._per_server[guild_id]
        try:
            yield
        finally:
            self._sem.release()
