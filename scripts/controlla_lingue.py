"""
scripts/controlla_lingue.py
===========================
Per ogni lingua in `locales/`: chiavi mancanti, uguali all'italiano e segnaposto diversi.
Scrive il riepilogo in `locales/RIEPILOGO.md` e lo stampa. Uso: `python3 scripts/controlla_lingue.py`.
Funzioni coperte: SPEC §21 (NF-06, #77, D58).
"""

from __future__ import annotations

import pathlib
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))


def main() -> int:
    from core.lingue_controllo import controlla, riepilogo

    testo = riepilogo(controlla())
    (RADICE / "locales" / "RIEPILOGO.md").write_text(testo, encoding="utf-8")
    print(testo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
