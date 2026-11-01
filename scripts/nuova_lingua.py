"""
scripts/nuova_lingua.py
=======================
Crea `locales/<codice>/` con tutte le chiavi vuote («da tradurre»). Uso: `python3 scripts/nuova_lingua.py pt-BR`.
Dopo: aggiungere il codice a `LINGUE` in `core/i18n.py` (e, per salvarlo come lingua personale, una migrazione
che allarga il CHECK di `user_language`).
Funzioni coperte: SPEC §21 (NF-06, #77, D58).
"""

from __future__ import annotations

import pathlib
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Uso: python3 scripts/nuova_lingua.py <codice>   (codice di Discord, es. pt-BR)")
        return 2
    from core.lingue_controllo import crea_lingua

    try:
        scritti = crea_lingua(argv[1])
    except ValueError as exc:
        print(exc)
        return 1
    print("Creati: " + ", ".join(scritti))
    print("Ora aggiungi il codice a LINGUE in core/i18n.py. Le chiavi vuote usano il ripiego (lingua -> en-US -> it).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
