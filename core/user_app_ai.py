"""
core/user_app_ai.py
===================
Le richieste all'AI di iYokai App (SPEC §B.2: Traduci, Spiega o riassumi) passano dallo snodo comune
(`core/ai_servizio.py`). Fuori da un server l'AI usa solo fornitori gratuiti, senza quote del server: vale il
limite al minuto della persona. Il testo di un messaggio non si salva né si riusa per altri (niente cache).
Funzioni coperte: SPEC §B.2 (NF-36, #107)
Dipende da: core/ai_servizio.py
"""

from __future__ import annotations

import logging

from core.ai_servizio import AINonDisponibile, RichiestaAI, servizio_ai
from core.user_app_messaggi import MAX_TESTO_AI

logger = logging.getLogger("iyokai.user_app_ai")


async def chiedi_ai_app(
    user_id: int, funzione: str, tipo: str, testo: str, istruzioni: str, lingua: str
) -> tuple[str | None, str | None]:
    """(testo dell'AI, None) oppure (None, motivo da mostrare): ogni funzione risponde sempre."""
    richiesta = RichiestaAI(
        user_id=user_id, funzione=funzione, tipo=tipo, testo=testo[:MAX_TESTO_AI], guild_id=None,
        istruzioni=istruzioni, messaggi_utenti=True, lingua=lingua, riusa=False,
    )
    try:
        risposta = await servizio_ai().richiedi(richiesta)
    except AINonDisponibile as exc:
        return None, exc.testo
    except Exception:  # noqa: BLE001 - database o fornitori in errore: si risponde senza AI
        logger.warning("Richiesta AI dell'app %s non riuscita.", funzione, exc_info=True)
        return None, AINonDisponibile("fornitori_fermi").testo
    return (risposta.testo or None), (None if risposta.testo else AINonDisponibile("fornitori_fermi").testo)
