"""
core/web_panel_panoramica.py
============================
La pagina iniziale di un server nel pannello: stato dei sistemi (moduli accesi e spenti), problemi trovati
(i consigli del punteggio di sicurezza, gli stessi di `/admin-sicurezza score`) e azioni rapide.
Funzioni coperte: SPEC §24.8 (CFG-003, issue #122)
Dipende da: core/security_logic.py, cogs/security/security_score.py (raccolta dei segnali)
"""

from __future__ import annotations

import asyncio
import logging

from core.security_logic import compute_security_score

logger = logging.getLogger("iyokai.web_panel_panoramica")

TEMPO_MASSIMO_SEGNALI = 5.0
MAX_CONSIGLI = 15
MAX_SPENTI = 40

# (titolo, percorso relativo al server, serve la scrittura)
AZIONI_RAPIDE = (
    ("Impostazioni dei moduli", "", False),
    ("Chi usa il pannello", "/accesso", False),
    ("Vocali temporanei", "/vocali", False),
    ("Statistiche pubbliche", "/statistiche", False),
    ("Classifica web", "/classifica", False),
    ("Chiave API", "/api", False),
    ("Avvisi del pannello", "/avvisi", False),
    ("Storico delle modifiche", "/storico", False),
)


def riassumi_moduli(moduli: list[dict]) -> dict:
    """Quanti moduli accesi e quali spenti (con tetto: la pagina non cresce con il numero dei moduli)."""
    accesi = [m for m in moduli if m["attivo"]]
    spenti = sorted((m for m in moduli if not m["attivo"]), key=lambda m: m["titolo"].lower())
    return {
        "totale": len(moduli), "accesi": len(accesi), "spenti": [m["titolo"] for m in spenti[:MAX_SPENTI]],
        "altri_spenti": max(0, len(spenti) - MAX_SPENTI),
    }


async def problemi_trovati(guild) -> tuple[int | None, tuple[str, ...]]:
    """(punteggio, consigli). Se i segnali non arrivano in tempo (server grande) il punteggio manca: mai un errore."""
    from cogs.security.security_score import _collect_signals

    try:
        segnali = await asyncio.wait_for(_collect_signals(guild), TEMPO_MASSIMO_SEGNALI)
        punteggio, consigli = compute_security_score(segnali)
    except Exception:  # noqa: BLE001 - la pagina iniziale deve aprirsi comunque
        logger.warning("Punteggio di sicurezza non calcolato per il server %s.", guild.id, exc_info=True)
        return None, ()
    return punteggio, consigli[:MAX_CONSIGLI]
