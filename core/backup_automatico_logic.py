"""
core/backup_automatico_logic.py
===============================
Copie automatiche della struttura del server a intervalli (da 3 ore a 7 giorni: SIC-016), con da 1 a 8 copie
tenute: la più vecchia automatica si sovrascrive, le copie fatte a mano non si toccano.
Funzioni coperte: BKP-008, SIC-016
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core import backup_struttura_logic as struttura
from core.repositories.backup_automatico_repo import backup_automatico_repo
from core.repositories.backup_struttura_repo import backup_struttura_repo

logger = logging.getLogger("iyokai.backup_automatico")


async def fai_copia_automatica(bot) -> bool:
    """Una copia per il server più in ritardo. True se ne ha salvata una. Mai solleva per un server solo."""
    dovuto = await backup_automatico_repo.prossimo_dovuto()
    if dovuto is None:
        return False
    guild = bot.get_guild(dovuto.guild_id)
    # Anche se non si può fare, si segna: un server assente non blocca gli altri a ogni giro.
    await backup_automatico_repo.segna(dovuto.guild_id)
    if guild is None:
        return False
    dati = struttura.leggi_struttura(guild)
    if len(struttura.in_json(dati)) > struttura.MAX_FILE_BYTE:
        logger.warning("Copia automatica di %s oltre 10 MiB: saltata.", dovuto.guild_id)
        return False
    nome = "auto " + datetime.now(timezone.utc).strftime("%d/%m %H:%M")
    copia = await backup_struttura_repo.salva_automatica(dovuto.guild_id, nome, dati, dovuto.copie)
    return copia is not None
