"""
cogs/ai/_privacy_ai.py
======================
Per l'owner: ogni richiesta di cancellazione dei dati in attesa riceve una riga di riassunto e un'azione proposta
dall'AI. L'AI non cancella nulla: `/owner privacy approva` e `rifiuta` restano a mano. Il motivo scritto dalla persona
passa dallo snodo come testo di utente (D19). Aiuto per altri cog: nessun comando.
Funzioni coperte: SPEC §25.84 (AI-R-091)
"""

from __future__ import annotations

import logging

from cogs.ai._comune import chiedi
from core import ai_privacy_logic as logica
from core.ai_servizio import RichiestaAI
from core.config import config

logger = logging.getLogger("iyokai.ai_privacy")


async def proposta_per(motivo: str | None) -> logica.Proposta:
    """La proposta dell'AI per una richiesta; se l'AI non c'è o sbaglia, quella fissa."""
    if not (motivo and motivo.strip()):
        return logica.proposta_locale(motivo)  # niente testo da leggere: non serve l'AI
    risposta, _ = await chiedi(RichiestaAI(
        user_id=config.OWNER_ID, funzione="privacy_richiesta", tipo="giudizio", testo=motivo[:300], guild_id=None,
        istruzioni=logica.ISTRUZIONI, messaggi_utenti=True, conta_utente=False, riusa=False,
    ))
    return (logica.leggi_proposta(risposta.testo) if risposta else None) or logica.proposta_locale(motivo)

