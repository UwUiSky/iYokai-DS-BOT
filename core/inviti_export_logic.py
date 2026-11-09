"""
core/inviti_export_logic.py
===========================
Esportazione degli inviti in CSV o JSON (D69 B13): righe semplici in byte, entro il limite degli allegati.
Una cella che comincia con =, +, -, @ si neutralizza (i fogli di calcolo la prenderebbero per una formula).
Funzioni coperte: catalogo UTL-183
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime

MAX_BYTE_ALLEGATO = 8 * 1024 * 1024  # sotto i 10 MiB di Discord (LIM-55)
FORMATI = ("csv", "json")


def _valore(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def neutralizza_cella(v) -> str:
    testo = "" if v is None else str(_valore(v))
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return testo  # un numero negativo (bonus -3) resta un numero: non è una formula
    return "'" + testo if testo[:1] in ("=", "+", "-", "@", "\t", "\r") else testo


def costruisci(righe: list[dict], colonne: list[str], formato: str) -> tuple[bytes, int]:
    """(byte, righe messe). Se supera il limite si tagliano le righe in fondo: il secondo numero lo dice."""
    if formato not in FORMATI:
        raise ValueError("formato sconosciuto")
    messe = len(righe)
    while True:
        dati = _scrivi(righe[:messe], colonne, formato)
        if len(dati) <= MAX_BYTE_ALLEGATO or messe == 0:
            return dati, messe
        messe = messe * 9 // 10


def _scrivi(righe: list[dict], colonne: list[str], formato: str) -> bytes:
    if formato == "json":
        return json.dumps(
            [{c: _valore(r.get(c)) for c in colonne} for r in righe], ensure_ascii=False, indent=1
        ).encode("utf-8")
    uscita = io.StringIO()
    scrittore = csv.writer(uscita)
    scrittore.writerow(colonne)
    for r in righe:
        scrittore.writerow([neutralizza_cella(r.get(c)) for c in colonne])
    return uscita.getvalue().encode("utf-8")
