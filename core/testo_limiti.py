"""
core/testo_limiti.py
====================
Limiti di testo di Discord per gli embed e un unico modo di tagliare un testo.
Funzioni coperte: LIM-15
"""

from __future__ import annotations

CAMPO_MAX = 1024
DESCRIZIONE_MAX = 4096


def tronca(testo: str, limite: int) -> str:
    """Taglia a `limite` caratteri; se taglia, finisce con «…»."""
    if len(testo) <= limite:
        return testo
    return testo[: limite - 1] + "…"
