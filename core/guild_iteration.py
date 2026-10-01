"""
core/guild_iteration.py
=======================
Itera su server (o clan, utenti) dentro un worker periodico isolando gli
errori: un elemento problematico viene registrato nei log e saltato, il
giro continua per tutti gli altri.
Funzioni coperte: REVIEW.md LC-8.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Iterable, TypeVar

logger = logging.getLogger("iyokai.worker")

T = TypeVar("T")


async def for_each_guild_safely(
    elementi: Iterable[T],
    operazione: Callable[[T], Awaitable[None]],
    *,
    nome_worker: str,
) -> int:
    """
    Esegue `operazione` su ogni elemento. Se solleva, registra
    l'errore (con l'elemento) e passa al successivo. Restituisce quanti
    elementi sono falliti. La cancellazione del task non viene mai
    inghiottita.
    """
    falliti = 0
    for elemento in elementi:
        try:
            await operazione(elemento)
        except asyncio.CancelledError:
            raise
        except Exception:
            falliti += 1
            logger.exception(
                "%s: errore su %s, passo al successivo.",
                nome_worker,
                getattr(elemento, "id", elemento),
            )
    return falliti
