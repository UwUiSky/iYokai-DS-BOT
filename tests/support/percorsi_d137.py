"""
tests/support/percorsi_d137.py
==============================
La mappa del riordino D137 (migrazione 0972) letta dal file SQL: serve ai test delle migrazioni più vecchie, i cui percorsi
"nuovi" possono essere stati spostati ancora dal riordino.
"""

from __future__ import annotations

import re
from pathlib import Path

_SQL = (Path(__file__).resolve().parent.parent.parent / "core/migrations/0972_percorsi_comandi_riordino_d137.sql").read_text()
D137: dict[str, str] = dict(re.findall(r"^    \('([^']+)', '([^']+)'\)", _SQL, re.M))
IMMAGINI_D137: frozenset[str] = frozenset(D137.values())


def dopo_d137(percorso: str) -> str:
    """Il percorso com'è dopo il riordino D137 (lo stesso se non è stato spostato)."""
    return D137.get(percorso, percorso)
