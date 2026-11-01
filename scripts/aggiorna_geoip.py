"""
scripts/aggiorna_geoip.py
=========================
Scarica la banca dati dei paesi (DB-IP «IP to Country Lite», formato MMDB, licenza CC BY 4.0,
https://db-ip.com) per la verifica web (D53). Lo lancia l'owner, di solito una volta al mese.
Uso: python3 scripts/aggiorna_geoip.py [percorso]   (di base `data/geoip/dbip-country-lite.mmdb`)
Poi metti il percorso in `GEOIP_PAESI_MMDB` nel `.env`.
Funzioni coperte: SPEC §4.2 (paese, D53)
"""

from __future__ import annotations

import gzip
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date

PERCORSO_DI_BASE = "data/geoip/dbip-country-lite.mmdb"
INDIRIZZO = "https://download.db-ip.com/free/dbip-country-lite-{anno}-{mese:02d}.mmdb.gz"


def mesi_da_provare(oggi: date) -> list[tuple[int, int]]:
    """Il mese corrente e quello prima (il file del mese nuovo esce qualche giorno dopo l'inizio)."""
    precedente = (oggi.year - 1, 12) if oggi.month == 1 else (oggi.year, oggi.month - 1)
    return [(oggi.year, oggi.month), precedente]


def scarica(destinazione: str) -> str:
    cartella = os.path.dirname(os.path.abspath(destinazione))
    os.makedirs(cartella, exist_ok=True)
    ultimo_errore: Exception | None = None
    for anno, mese in mesi_da_provare(date.today()):
        indirizzo = INDIRIZZO.format(anno=anno, mese=mese)
        try:
            with urllib.request.urlopen(indirizzo, timeout=120) as risposta, tempfile.NamedTemporaryFile(
                dir=cartella, delete=False
            ) as temporaneo:
                with gzip.GzipFile(fileobj=risposta) as dati:
                    shutil.copyfileobj(dati, temporaneo)
            _controlla(temporaneo.name)
            os.replace(temporaneo.name, destinazione)  # sostituzione intera: il bot non legge mai un file a metà
            return indirizzo
        except (urllib.error.URLError, OSError, ValueError) as errore:
            ultimo_errore = errore
    raise SystemExit(f"Scaricamento non riuscito: {ultimo_errore}")


def _controlla(percorso: str) -> None:
    import maxminddb

    with maxminddb.open_database(percorso) as lettore:
        if lettore.get("8.8.8.8") is None:
            raise ValueError("la banca dati scaricata non è valida")


if __name__ == "__main__":
    destinazione = sys.argv[1] if len(sys.argv) > 1 else PERCORSO_DI_BASE
    print(f"Scaricato da {scarica(destinazione)}")
    print(f"Salvato in {destinazione}. Metti questo percorso in GEOIP_PAESI_MMDB nel .env.")
    print("Dati IP to Country Lite di DB-IP.com, licenza CC BY 4.0.")
