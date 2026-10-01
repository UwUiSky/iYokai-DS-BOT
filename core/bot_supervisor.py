"""
core/bot_supervisor.py
======================
Avvio isolato dei bot nello stesso processo e spegnimento ordinato:
un bot secondario che cade non ferma gli altri, la caduta del principale
fa uscire il processo con un errore, e su SIGTERM/SIGINT si chiude tutto
in ordine (bot, sessioni HTTP, database).
Funzioni coperte: REVIEW.md BUG-7 (issue #12, #28).
"""

from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass
from typing import Awaitable, Callable

logger = logging.getLogger("iyokai.supervisor")


@dataclass(frozen=True)
class VoceBot:
    """Un bot da avviare. `critico=True` solo per il bot principale."""

    nome: str
    avvio: Callable[[], Awaitable[None]]
    critico: bool = False


async def _supervisore(voce: VoceBot, notifica) -> None:
    try:
        await voce.avvio()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Il bot '%s' si è fermato per un errore", voce.nome)
        if voce.critico:
            raise  # il processo deve uscire con un errore
        if notifica is not None:
            try:
                await notifica(f"⚠️ Il bot '{voce.nome}' si è fermato per un errore. Vedi i log.")
            except Exception:
                logger.warning("Impossibile avvisare l'owner della caduta di '%s'.", voce.nome)


async def esegui_bot_isolati(voci: list[VoceBot], notifica=None) -> None:
    """
    Avvia ogni bot in un task proprio. Un bot non critico che cade viene
    solo registrato (e segnalato con `notifica`); finisce quando finisce
    il bot critico, e allora ferma tutti gli altri.
    """
    critici = [v for v in voci if v.critico]
    assert len(critici) == 1, "serve esattamente un bot critico"

    task_critico = None
    altri = []
    for voce in voci:
        task = asyncio.create_task(_supervisore(voce, notifica), name=voce.nome)
        if voce.critico:
            task_critico = task
        else:
            altri.append(task)

    try:
        await task_critico
    finally:
        task_critico.cancel()
        for task in altri:
            task.cancel()
        await asyncio.gather(task_critico, *altri, return_exceptions=True)


async def spegni_ordinatamente(clients, chiusure_sessioni, chiudi_database) -> None:
    """
    Chiude in quest'ordine: i bot (che fermano anche i loop dei cog),
    le sessioni HTTP condivise, il pool del database. Un errore in un
    passo viene registrato e non salta i passi successivi.
    """
    for client in clients:
        try:
            await client.close()
        except Exception:
            logger.exception("Errore nella chiusura di un bot")
    for chiudi in chiusure_sessioni:
        try:
            await chiudi()
        except Exception:
            logger.exception("Errore nella chiusura di una sessione HTTP")
    try:
        await chiudi_database()
    except Exception:
        logger.exception("Errore nella chiusura del database")


def installa_gestori_segnali(task: asyncio.Task) -> None:
    """SIGTERM/SIGINT cancellano il task principale (poi parte lo spegnimento)."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, task.cancel)
        except NotImplementedError:
            pass  # Windows: Ctrl+C è già gestito da asyncio.run
