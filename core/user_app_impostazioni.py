"""
core/user_app_impostazioni.py
=============================
Le impostazioni personali di iYokai App lette dai comandi (SPEC §B.10): risposte private o pubbliche,
DM sì o no, storico acceso, profilo globale visibile agli altri. Se il database non risponde valgono i
valori più prudenti (private, DM sì, storico spento, profilo non pubblico).
Funzioni coperte: SPEC §B.10 (NF-36, #107)
Dipende da: core/repositories/user_app_repo.py
"""

from __future__ import annotations

import logging

from core.repositories.user_app_repo import Impostazioni, user_app_repo

logger = logging.getLogger("iyokai.user_app")


async def impostazioni_di(user_id: int) -> Impostazioni:
    try:
        return await user_app_repo.impostazioni(user_id)
    except Exception:  # noqa: BLE001 - un'impostazione non letta non ferma il comando
        logger.warning("Impostazioni dell'app non lette.", exc_info=True)
        return Impostazioni()


async def risposta_privata(user_id: int) -> bool:
    """True se le risposte dei comandi devono vedersi solo da chi li usa."""
    return (await impostazioni_di(user_id)).risposte_private
