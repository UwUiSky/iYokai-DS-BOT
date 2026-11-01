"""
core/geoip_paesi.py
===================
Paese da un IP con una banca dati locale in formato MMDB (DB-IP «IP to Country Lite»,
CC BY 4.0, o GeoLite2 Country), letta con `maxminddb`. Nessun servizio esterno. Serve
solo durante la verifica web (D53): l'IP resta in memoria e torna solo il codice del paese.
Il percorso del file è in `GEOIP_PAESI_MMDB`; senza file la funzione è spenta, senza errori.
Funzioni coperte: SPEC §4.2 (paese, D53)
"""

from __future__ import annotations

import logging
import os

from core.verify_paese_logic import codice_da_record

logger = logging.getLogger("iyokai.geoip")

_lettore = None
_provato = False


def usa_lettore(lettore) -> None:
    """Per i test: un lettore già pronto (con `get(ip)`)."""
    global _lettore, _provato
    _lettore, _provato = lettore, True


def _apri():
    global _lettore, _provato
    if _provato:
        return _lettore
    _provato = True
    percorso = os.environ.get("GEOIP_PAESI_MMDB", "").strip()
    if not percorso:
        return None
    try:
        import maxminddb

        _lettore = maxminddb.open_database(percorso)
    except Exception:  # file assente, rotto o libreria mancante: funzione spenta
        logger.warning("Banca dati dei paesi non utilizzabile: il paese nella verifica resta spento.")
        _lettore = None
    return _lettore


def attiva() -> bool:
    return _apri() is not None


def paese_da_ip(ip: str | None) -> str | None:
    """Il codice ISO del paese, o None (funzione spenta, IP non in banca dati, errore)."""
    if not ip:
        return None
    lettore = _apri()
    if lettore is None:
        return None
    try:
        return codice_da_record(lettore.get(ip))
    except Exception:
        return None
