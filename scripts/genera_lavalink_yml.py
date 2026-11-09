"""
scripts/genera_lavalink_yml.py
==============================
Scrive deploy/lavalink/application.yml dalle fonti accese e dalle chiavi presenti
nell'ambiente. Il file ha solo segnaposto ${VARIABILE}: nessun valore di chiave.

Uso:
    python3 scripts/genera_lavalink_yml.py              # scrive il file
    python3 scripts/genera_lavalink_yml.py --stampa     # lo mostra soltanto
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lavalink_yml import genera_application_yml

DESTINAZIONE = Path(__file__).resolve().parent.parent / "deploy" / "lavalink" / "application.yml"


def main() -> None:
    testo = genera_application_yml()
    if "--stampa" in sys.argv:
        print(testo)
        return
    DESTINAZIONE.write_text(testo, encoding="utf-8")
    print(f"Scritto {DESTINAZIONE.name} (solo segnaposto, nessuna chiave).")


if __name__ == "__main__":
    main()
