"""
core/auto_foto_controllo.py
===========================
Controllo automatico delle foto delle auto per contenuti per adulti (FUN-017, D122). La foto, già ricodificata in
sandbox (D74), va allo snodo AI (`ServizioAI.modera_immagine`), mai a un servizio chiamato direttamente. Tre esiti:
«adulti» (rifiutata o tolta), «pulita» (passa e si segna come controllata), «non disponibile» (nessun fornitore di
moderazione o servizio fermo: passa come prima, con segnalazioni e staff, D123).
Funzioni coperte: SPEC §24 (FUN-017, D122, D123)
Dipende da: core/ai_servizio.py
"""

from __future__ import annotations

import logging

from core.ai_servizio import servizio_ai

logger = logging.getLogger("iyokai.auto_foto_controllo")

ADULTI = "adulti"
PULITA = "pulita"
NON_DISPONIBILE = "non_disponibile"


async def controlla(png: bytes, guild_id: int | None) -> str:
    """L'esito del controllo. Non solleva mai: un controllo che non riesce vale «non disponibile»."""
    try:
        adulti = await servizio_ai().modera_immagine(png, guild_id)
    except Exception:  # noqa: BLE001
        logger.warning("Controllo della foto non riuscito.", exc_info=True)
        return NON_DISPONIBILE
    if adulti is None:
        return NON_DISPONIBILE
    return ADULTI if adulti else PULITA
