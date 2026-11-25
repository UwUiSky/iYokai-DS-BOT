"""
core/bot_supervisor.py
======================
Avvio isolato dei bot nello stesso processo e spegnimento ordinato:
un bot secondario che cade non ferma gli altri, la caduta del principale
fa uscire il processo con un errore, e su SIGTERM/SIGINT si chiude tutto
in ordine (servizi periodici, bot, sessioni HTTP, database). Un secondo
segnale arrivato a chiusura iniziata viene ignorato.
Funzioni coperte: REVIEW.md BUG-7 (issue #12, #28).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import discord

from core.giro_periodico import pausa_dopo_errori
from core.i18n import t

logger = logging.getLogger("iyokai.supervisor")


@dataclass(frozen=True)
class VoceBot:
    """Un bot da avviare. `critico=True` solo per il bot principale."""

    nome: str
    avvio: Callable[[], Awaitable[None]]
    critico: bool = False


# Un bot secondario che resta su così a lungo dopo un riavvio è tornato davvero: si azzera il conto degli errori.
STABILE_DOPO_SECONDI = 300.0


async def _supervisore(voce: VoceBot, notifica, notifica_ripresa=None, pausa=pausa_dopo_errori) -> None:
    """
    Tiene su un bot. Il principale che cade fa uscire il processo. Un bot secondario che cade (o si chiude
    da solo) riparte con pause crescenti (5 s, 10 s, ... fino a 15 minuti): un solo avviso all'owner per
    serie di cadute, e uno quando torna stabile. Un token sbagliato non si riprova: sarebbe inutile.
    """
    errori = 0
    avvisato = False
    while True:
        inizio = time.monotonic()
        try:
            await voce.avvio()
            if voce.critico:
                return
            logger.warning("Il bot '%s' si è chiuso: lo riavvio.", voce.nome)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Il bot '%s' si è fermato per un errore", voce.nome)
            if voce.critico:
                raise  # il processo deve uscire con un errore
            if isinstance(exc, discord.LoginFailure):
                await _avvisa(notifica, t("owner_bot_token_errato", nome=voce.nome))
                return  # il token è sbagliato: riprovare non serve
        if time.monotonic() - inizio >= STABILE_DOPO_SECONDI:
            if avvisato and notifica_ripresa is not None:
                await _avvisa(notifica_ripresa, t("owner_bot_tornato", nome=voce.nome))
            errori, avvisato = 0, False
        errori += 1
        if not avvisato:
            avvisato = True
            await _avvisa(notifica, t("owner_bot_fermato", nome=voce.nome))
        attesa = pausa(errori)
        logger.info("Il bot '%s' riparte tra %.0f secondi.", voce.nome, attesa)
        await asyncio.sleep(attesa)


async def _avvisa(notifica, testo: str) -> None:
    if notifica is None:
        return
    try:
        await notifica(testo)
    except Exception:
        logger.warning("Impossibile avvisare l'owner (DM chiusi o Discord non raggiungibile).")


async def esegui_bot_isolati(voci: list[VoceBot], notifica=None, notifica_ripresa=None) -> None:
    """
    Avvia ogni bot in un task proprio. Un bot non critico che cade viene segnalato con `notifica`
    e riavviato con pause crescenti (`notifica_ripresa` quando torna); finisce quando finisce
    il bot critico, e allora ferma tutti gli altri.
    """
    critici = [v for v in voci if v.critico]
    assert len(critici) == 1, "serve esattamente un bot critico"

    task_critico = None
    altri = []
    for voce in voci:
        task = asyncio.create_task(_supervisore(voce, notifica, notifica_ripresa), name=voce.nome)
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


async def ferma_servizi_periodici(servizi) -> None:
    """
    Ferma il tasks.loop dei servizi di core/ (ognuno lo tiene in
    `_loop_task`) e aspetta che siano davvero finiti: dopo, nessun giro
    può più usare il database o i bot. Un servizio mai avviato si salta.
    """
    in_chiusura = []
    for servizio in servizi:
        loop_task = servizio._loop_task
        if loop_task is None:
            continue
        loop_task.cancel()
        if loop_task.get_task() is not None:
            in_chiusura.append(loop_task.get_task())
        servizio._loop_task = None
    await asyncio.gather(*in_chiusura, return_exceptions=True)


async def spegni_ordinatamente(clients, chiusure_sessioni, chiudi_database, servizi=()) -> None:
    """
    Chiude in quest'ordine: i servizi periodici di core/, i bot (che
    fermano anche i loop dei cog), le sessioni HTTP condivise, il pool
    del database. Un errore in un passo viene registrato e non salta i
    passi successivi.
    """
    try:
        await ferma_servizi_periodici(servizi)
    except Exception:
        logger.exception("Errore nell'arresto dei servizi periodici")
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


def _segnale_ignorato() -> None:
    logger.warning("Segnale di arresto ricevuto, ma la chiusura già in corso non si interrompe.")


def _imposta_gestore_segnali(gestore) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, gestore)
        except NotImplementedError:
            pass  # Windows: Ctrl+C è già gestito da asyncio.run


def installa_gestori_segnali(task: asyncio.Task) -> None:
    """SIGTERM/SIGINT cancellano il task principale (poi parte lo spegnimento)."""
    _imposta_gestore_segnali(task.cancel)


def ignora_altri_segnali() -> None:
    """
    Da chiamare appena inizia lo spegnimento: un secondo SIGTERM/SIGINT
    cancellerebbe la chiusura stessa a metà (un solo bot chiuso, pool del
    database lasciato aperto). Da qui in poi i segnali vengono solo
    registrati.
    """
    _imposta_gestore_segnali(_segnale_ignorato)
