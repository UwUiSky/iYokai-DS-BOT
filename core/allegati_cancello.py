"""
core/allegati_cancello.py
=========================
Cancello dei download degli allegati dei log (blocco B): PRIMA di scaricare i byte si controlla che ci sia posto.
Tetti: 4 download insieme in tutto il bot, al massimo 16 in attesa, 48 MiB di byte dichiarati in volo, e la coda
della sandbox sotto la meta' (50 lavori su 100). Sopra soglia l'allegato non si scarica: resta solo la scheda,
senza byte. Cosi' un raid di immagini non porta il processo in OOM e non riempie la coda della sandbox.
Funzioni coperte: SPEC §6 (D62), §8.16 (D74); SICUREZZA.md §7
Dipende da: core/immagini_coda.py (la coda della sandbox)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from core.immagini_coda import MAX_TOTALE, coda_immagini

CONTEMPORANEI = 4
MAX_IN_ATTESA = 16
MAX_BYTE_IN_VOLO = 48 * 1024 * 1024
SOGLIA_CODA_SANDBOX = MAX_TOTALE // 2


class CancelloDownload:
    def __init__(
        self, contemporanei: int = CONTEMPORANEI, max_in_attesa: int = MAX_IN_ATTESA,
        max_byte: int = MAX_BYTE_IN_VOLO, soglia_coda: int = SOGLIA_CODA_SANDBOX,
    ) -> None:
        self._semaforo = asyncio.Semaphore(contemporanei)
        self.max_in_attesa = max_in_attesa
        self.max_byte = max_byte
        self.soglia_coda = soglia_coda
        self.in_attesa = 0  # prenotati: in attesa o in corso
        self.byte_in_volo = 0

    def _ha_posto(self, dimensione: int, coda_sandbox: int) -> bool:
        return (
            coda_sandbox < self.soglia_coda
            and self.in_attesa < self.max_in_attesa
            and self.byte_in_volo + max(0, dimensione) <= self.max_byte
        )

    @asynccontextmanager
    async def posto(self, dimensione: int) -> AsyncIterator[bool]:
        """
        `async with cancello.posto(a.size) as ok:` Se `ok` e' falso non si scarica nulla. Se e' vero si ha un posto per
        scaricare e dare i byte alla sandbox; il posto si libera all'uscita, anche con un errore.
        """
        if not self._ha_posto(dimensione, coda_immagini.in_coda):
            yield False
            return
        self.in_attesa += 1
        self.byte_in_volo += max(0, dimensione)
        try:
            async with self._semaforo:
                yield True
        finally:
            self.in_attesa -= 1
            self.byte_in_volo -= max(0, dimensione)


cancello = CancelloDownload()
