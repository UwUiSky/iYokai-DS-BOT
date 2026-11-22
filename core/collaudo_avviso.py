"""
core/collaudo_avviso.py
=======================
Avviso all'avvio del bot: con COLLAUDO=1 e un terminale vero, ricorda di aprire
`scripts/collaudo.py` in un altro terminale. Non lancia nulla (D109).
Funzioni coperte: #94
"""

from __future__ import annotations

import os
import sys


def messaggio_collaudo(env: dict | None = None, tty: bool | None = None) -> str | None:
    """Il testo da mostrare, o None se il collaudo non è acceso."""
    env = os.environ if env is None else env
    if tty is None:
        try:
            tty = sys.stdin.isatty()
        except (AttributeError, ValueError):
            tty = False
    if env.get("COLLAUDO", "").strip() != "1" or not tty:
        return None
    return ("Collaudo acceso (COLLAUDO=1): per le prove dal vivo apri un ALTRO terminale "
            "e lancia `python scripts/collaudo.py`.")
