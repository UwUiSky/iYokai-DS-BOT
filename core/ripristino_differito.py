"""
core/ripristino_differito.py
============================
Lavori che servono dopo l'avvio ma NON devono bloccarlo (per esempio rimettere le view dei
bottoni dei messaggi già pubblicati, che si leggono dal database). Il `setup()` di un cog
non fa mai I/O: se il database è lento l'avvio resterebbe fermo e i comandi sparirebbero.
Qui il lavoro gira in background e, se fallisce, riprova con pause crescenti (5 s ... 15 min).
Funzioni coperte: consiglio 25/11/2026, critico 6 (blocco C)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from core.giro_periodico import pausa_dopo_errori

logger = logging.getLogger(__name__)

# Riferimenti ai compiti: senza, asyncio può cancellarli perché nessuno li tiene.
_COMPITI: set[asyncio.Task] = set()


async def _ripeti_finche_riesce(nome: str, lavoro: Callable[[], Awaitable[None]]) -> None:
    errori = 0
    while True:
        try:
            await lavoro()
            if errori:
                logger.info("Ripristino %s riuscito dopo %d errori.", nome, errori)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            errori += 1
            pausa = pausa_dopo_errori(errori)
            logger.exception("Ripristino %s fallito (%d), riprovo tra %.0f s.", nome, errori, pausa)
            await asyncio.sleep(pausa)


def ripristina_in_background(nome: str, lavoro: Callable[[], Awaitable[None]]) -> asyncio.Task:
    """Fa partire `lavoro` in background e lo ripete finché non riesce. Il lavoro deve reggere una seconda esecuzione."""
    compito = asyncio.get_running_loop().create_task(_ripeti_finche_riesce(nome, lavoro), name=f"ripristino: {nome}")
    _COMPITI.add(compito)
    compito.add_done_callback(_COMPITI.discard)
    return compito


def ferma_ripristini() -> None:
    """Allo spegnimento: ferma i ripristini ancora in corso."""
    for compito in list(_COMPITI):
        compito.cancel()
