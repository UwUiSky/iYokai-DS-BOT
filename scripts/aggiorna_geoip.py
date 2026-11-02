"""
scripts/aggiorna_geoip.py
=========================
Scarica le banche dati di DB-IP in formato MMDB (licenza CC BY 4.0, https://db-ip.com) per la verifica
web: i paesi («IP to Country Lite», D53) e gli ASN («IP to ASN Lite», D64). Lo lancia l'owner, di
solito una volta al mese.
Uso: python3 scripts/aggiorna_geoip.py [percorso paesi [percorso ASN]]
(di base `data/geoip/dbip-country-lite.mmdb` e `data/geoip/dbip-asn-lite.mmdb`)
Poi metti i percorsi in `GEOIP_PAESI_MMDB` e `GEOIP_ASN_MMDB` nel `.env`.
Funzioni coperte: SPEC §4.2 (paese, D53; VPN e proxy, D64)
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
PERCORSO_ASN_DI_BASE = "data/geoip/dbip-asn-lite.mmdb"
INDIRIZZO = "https://download.db-ip.com/free/dbip-country-lite-{anno}-{mese:02d}.mmdb.gz"
INDIRIZZO_ASN = "https://download.db-ip.com/free/dbip-asn-lite-{anno}-{mese:02d}.mmdb.gz"


def mesi_da_provare(oggi: date) -> list[tuple[int, int]]:
    """Il mese corrente e quello prima (il file del mese nuovo esce qualche giorno dopo l'inizio)."""
    precedente = (oggi.year - 1, 12) if oggi.month == 1 else (oggi.year, oggi.month - 1)
    return [(oggi.year, oggi.month), precedente]


def scarica(destinazione: str, modello: str | None = None, controllo=None) -> str:
    cartella = os.path.dirname(os.path.abspath(destinazione))
    os.makedirs(cartella, exist_ok=True)
    ultimo_errore: Exception | None = None
    modello = modello or INDIRIZZO
    controllo = controllo or _controlla
    for anno, mese in mesi_da_provare(date.today()):
        indirizzo = modello.format(anno=anno, mese=mese)
        temporaneo = tempfile.NamedTemporaryFile(dir=cartella, suffix=".parziale", delete=False)
        try:
            with urllib.request.urlopen(indirizzo, timeout=120) as risposta, temporaneo:
                with gzip.GzipFile(fileobj=risposta) as dati:
                    shutil.copyfileobj(dati, temporaneo)
            controllo(temporaneo.name)
            os.replace(temporaneo.name, destinazione)  # sostituzione intera: il bot non legge mai un file a metà
            return indirizzo
        except (urllib.error.URLError, OSError, ValueError) as errore:
            ultimo_errore = errore
        finally:
            if os.path.exists(temporaneo.name):
                os.remove(temporaneo.name)  # niente resti a metà nella cartella
    raise SystemExit(f"Scaricamento non riuscito: {ultimo_errore}")


def _controlla(percorso: str) -> None:
    _controlla_chiave(percorso, "country")


def _controlla_asn(percorso: str) -> None:
    _controlla_chiave(percorso, "autonomous_system_number")


def _controlla_chiave(percorso: str, chiave: str) -> None:
    import maxminddb

    try:
        with maxminddb.open_database(percorso) as lettore:
            record = lettore.get("8.8.8.8")
            valida = isinstance(record, dict) and bool(record.get(chiave))
    except maxminddb.InvalidDatabaseError:
        valida = False
    if not valida:
        raise ValueError("la banca dati scaricata non è valida")


if __name__ == "__main__":
    destinazione = sys.argv[1] if len(sys.argv) > 1 else PERCORSO_DI_BASE
    destinazione_asn = sys.argv[2] if len(sys.argv) > 2 else PERCORSO_ASN_DI_BASE
    print(f"Scaricato da {scarica(destinazione)}")
    print(f"Salvato in {destinazione}. Metti questo percorso in GEOIP_PAESI_MMDB nel .env.")
    print(f"Scaricato da {scarica(destinazione_asn, INDIRIZZO_ASN, _controlla_asn)}")
    print(f"Salvato in {destinazione_asn}. Metti questo percorso in GEOIP_ASN_MMDB nel .env.")
    print("Dati IP to Country Lite e IP to ASN Lite di DB-IP.com, licenza CC BY 4.0.")
