"""
core/log_coda.py
================
I log vanno su disco da un thread a parte. Scrivere su file dal ciclo asyncio blocca tutto il bot quando il
disco è lento (un backup in corso, un disco pieno): qui chi scrive il log mette il messaggio in una coda e
basta, e un thread separato lo scrive su console e file. La coda ha un tetto: se si riempie, i messaggi nuovi
si scartano (e si contano) invece di fermare il bot.
Funzioni coperte: consiglio 25/11/2026, seri di stabilità (blocco C)
"""

from __future__ import annotations

import logging
import logging.handlers
import queue

TETTO_CODA = 20_000


class CodaLimitata(logging.handlers.QueueHandler):
    """Un QueueHandler che non blocca e non solleva mai: con la coda piena scarta il messaggio e lo conta."""

    def __init__(self, coda: queue.Queue) -> None:
        super().__init__(coda)
        self.scartati = 0

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.scartati += 1


class AscoltatoreCheAspetta(logging.handlers.QueueListener):
    """Allo stop il segnale di fine aspetta un posto in coda: con la coda piena `put_nowait` solleverebbe Full."""

    def enqueue_sentinel(self) -> None:
        self.queue.put(self._sentinel)


_ascoltatore: logging.handlers.QueueListener | None = None
_gestore_coda: CodaLimitata | None = None


def avvia_log_in_coda(handlers: list[logging.Handler], livello: int, tetto: int = TETTO_CODA) -> CodaLimitata:
    """Mette `handlers` (console, file) dietro una coda e li collega al logger principale."""
    global _ascoltatore, _gestore_coda
    ferma_log_in_coda()
    coda: queue.Queue = queue.Queue(maxsize=tetto)
    _gestore_coda = CodaLimitata(coda)
    _ascoltatore = AscoltatoreCheAspetta(coda, *handlers, respect_handler_level=True)
    _ascoltatore.start()
    logging.basicConfig(level=livello, handlers=[_gestore_coda], force=True)
    return _gestore_coda


def ferma_log_in_coda() -> None:
    """Allo spegnimento: scrive i messaggi rimasti in coda e ferma il thread."""
    global _ascoltatore, _gestore_coda
    if _ascoltatore is not None:
        _ascoltatore.stop()  # aspetta che la coda sia vuota
        _ascoltatore = None
    _gestore_coda = None
