"""
core/immagini_coda.py
=====================
Coda delle analisi immagine (D62): 100 lavori in tutto, 20 per server (un raid non ferma gli altri
server), un lavoro alla volta. Piena = `CodaPiena`: chi chiama decide cosa fare (i controlli sui
byte e la libreria delle impronte girano comunque). L'avviso all'owner ha un tetto di uno ogni 10 minuti.
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

MAX_TOTALE = 100
MAX_PER_SERVER = 20
SECONDI_TRA_AVVISI = 600


class CodaPiena(Exception):
    """Troppi lavori in attesa (in tutto, o per questo server)."""


class CodaImmagini:
    def __init__(self, max_totale: int = MAX_TOTALE, max_per_server: int = MAX_PER_SERVER, contemporanei: int = 1) -> None:
        self.max_totale = max_totale
        self.max_per_server = max_per_server
        self._per_server: Counter[int] = Counter()
        self._totale = 0
        self._semaforo = asyncio.Semaphore(contemporanei)
        self._ultimo_avviso = 0.0

    @property
    def in_coda(self) -> int:
        return self._totale

    def in_coda_per(self, guild_id: int) -> int:
        return self._per_server[guild_id]

    def puo_avvisare(self) -> bool:
        """Vero al massimo una volta ogni 10 minuti."""
        adesso = time.monotonic()
        if self._ultimo_avviso and adesso - self._ultimo_avviso < SECONDI_TRA_AVVISI:
            return False
        self._ultimo_avviso = adesso
        return True

    async def esegui(self, guild_id: int, lavoro: Callable[[], Awaitable[T]]) -> T:
        if self._totale >= self.max_totale or self._per_server[guild_id] >= self.max_per_server:
            raise CodaPiena(f"{self._totale} in coda, {self._per_server[guild_id]} per il server")
        self._totale += 1
        self._per_server[guild_id] += 1
        try:
            async with self._semaforo:
                return await lavoro()
        finally:
            self._totale -= 1
            self._per_server[guild_id] -= 1
            if not self._per_server[guild_id]:
                del self._per_server[guild_id]


coda_immagini = CodaImmagini()
