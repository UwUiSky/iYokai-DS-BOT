"""
core/desktop_eventi.py
======================
Chi produce un avviso per iYokai Desktop (promemoria, risposte dell'assistenza, avvisi dello staff) lo registra
da qui: si salva solo se la persona ha collegato il programma, così la tabella non si riempie per nessuno.
Qui c'è anche il controllo «la persona vede questo canale», comune agli avvisi e all'interfaccia del programma.
Funzioni coperte: SPEC D.5 (#108)
Dipende da: core/repositories/desktop_repo.py
"""

from __future__ import annotations

import logging

import discord

from core.desktop_logic import TIPI_EVENTO, testo_breve
from core.repositories.desktop_repo import desktop_repo

logger = logging.getLogger("iyokai.desktop")


def vede_il_canale(canale, membro) -> bool:
    """
    Il membro vede il canale. Un thread ha i permessi del canale padre: se è privato lo vede solo chi ne fa
    parte, chi l'ha aperto o chi gestisce i thread.
    """
    permessi = canale.permissions_for(membro)
    if not permessi.view_channel:
        return False
    if isinstance(canale, discord.Thread) and canale.is_private():
        return (
            canale.owner_id == membro.id
            or bool(getattr(permessi, "manage_threads", False))
            or canale.get_member(membro.id) is not None
        )
    return True


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
