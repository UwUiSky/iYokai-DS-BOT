"""
core/ticket_trascrizioni_servizio.py
====================================
Conservazione della trascrizione di un ticket alla chiusura (TKT-072, D111): se il server la vuole e la chiave c'è,
le pagine HTML (testo e immagini ricodificate) si cifrano e si salvano con la scadenza scelta (90 giorni al massimo).
Senza chiave non si salva niente, mai in chiaro. Non solleva: la chiusura del ticket non deve fallire per questo.
Funzioni coperte: SPEC §13.22 (TKT-072)
Dipende da: core/ticket_trascrizioni_logic.py, core/repositories/ticket_trascrizioni_repo.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core import ticket_trascrizioni_logic as logica
from core.config import config
from core.repositories.ticket_trascrizioni_repo import ticket_trascrizioni_repo as repo

logger = logging.getLogger("iyokai.ticket_trascrizioni")
_avvisato = False


async def attiva(guild_id: int) -> bool:
    """Il server la vuole (di base sì) e c'è una chiave per cifrarla."""
    global _avvisato
    if not logica.chiave_da_config(config):
        if not _avvisato:
            _avvisato = True
            logger.warning("Nessuna chiave per le trascrizioni dei ticket (TICKET_TRASCRIZIONI_KEY): non si conservano.")
        return False
    return (await repo.opzioni(guild_id)).attiva


async def conserva(guild_id: int, ticket, parti: list[str], adesso: datetime | None = None) -> int | None:
    """L'id della trascrizione salvata, o None se non si conserva o qualcosa è andato storto."""
    try:
        chiave = logica.chiave_da_config(config)
        if not chiave or not parti:
            return None
        opzioni = await repo.opzioni(guild_id)
        if not opzioni.attiva:
            return None
        cifrato = logica.cifra(parti, guild_id, ticket.id, chiave)
        return await repo.salva(
            guild_id, ticket.id, ticket.ticket_number or 0, ticket.user_id, ticket.panel_id, cifrato,
            logica.scadenza(adesso or datetime.now(timezone.utc), opzioni.giorni),
        )
    except Exception:  # noqa: BLE001 - la chiusura del ticket va avanti
        logger.warning("Trascrizione del ticket %s non conservata.", getattr(ticket, "id", "?"), exc_info=True)
        return None
