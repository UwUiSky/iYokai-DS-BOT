"""
core/desktop_eventi.py
======================
Chi produce un avviso per iYokai Desktop (promemoria, risposte dell'assistenza, avvisi dello staff) lo registra
da qui: si salva solo se la persona ha collegato il programma, così la tabella non si riempie per nessuno.
Funzioni coperte: SPEC D.5 (#108)
Dipende da: core/repositories/desktop_repo.py
"""

from __future__ import annotations

import logging

from core.desktop_logic import TIPI_EVENTO, testo_breve
from core.repositories.desktop_repo import desktop_repo

logger = logging.getLogger("iyokai.desktop")


async def avvisa_utente(user_id: int, tipo: str, testo: str, guild_id: int | None = None) -> bool:
    """True se l'avviso è stato messo in coda per il programma. Non solleva mai: un avviso perso non ferma nulla."""
    if tipo not in TIPI_EVENTO:
        raise ValueError(f"tipo di avviso sconosciuto: {tipo}")
    try:
        if not await desktop_repo.collegato(user_id):
            return False
        await desktop_repo.aggiungi_evento(user_id, tipo, guild_id=guild_id, testo=testo_breve(testo))
        return True
    except Exception:  # noqa: BLE001 - database fermo: l'avviso si perde, il resto continua
        logger.warning("Avviso per iYokai Desktop non registrato (%s, utente %s).", tipo, user_id, exc_info=True)
        return False
