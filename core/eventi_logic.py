"""
core/eventi_logic.py
====================
Regole degli eventi con iscrizioni, senza Discord: limiti, lettura della data, testi dei posti, pagine.
Funzioni coperte: catalogo #128 UTL-113 (D69, B24)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from core.duration_logic import parse_duration

MAX_TITOLO = 100
MAX_DESCRIZIONE = 1000
MAX_POSTI = 500
ANTICIPO_PROMEMORIA = 15 * 60
MIN_ANTICIPO = 60
MAX_ANTICIPO = 366 * 86400
PER_PAGINA = 15
MAX_NOMI_EMBED = 20
MAX_APERTI_PER_AUTORE = 10
FORMATI = ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M", "%d/%m/%y %H:%M")


def leggi_quando(testo: str, adesso: datetime, fuso: ZoneInfo) -> datetime | str:
    """Una data come `24/12/2026 21:00` (ora del `fuso`) o una durata come `3d`. Torna l'istante in UTC oppure il
    codice dell'errore: «formato», «passato», «lontano»."""
    pulito = " ".join(testo.split())
    quando = None
    for formato in FORMATI:
        try:
            quando = datetime.strptime(pulito, formato).replace(tzinfo=fuso).astimezone(timezone.utc)
            break
        except ValueError:
            continue
    if quando is None:
        try:
            quando = adesso + timedelta(seconds=parse_duration(pulito))
        except ValueError:
            return "formato"
    anticipo = (quando - adesso).total_seconds()
    if anticipo < MIN_ANTICIPO:
        return "passato"
    if anticipo > MAX_ANTICIPO:
        return "lontano"
    return quando


def testo_posti(si: int, posti: int | None) -> str:
    return f"{si}/{posti}" if posti else str(si)


def pagine(totale: int) -> int:
    return max(1, -(-totale // PER_PAGINA))


def promemoria_a(quando: datetime, adesso: datetime) -> datetime | None:
    """Quando mandare il promemoria (15 minuti prima), o None se l'evento è troppo vicino."""
    ora = quando - timedelta(seconds=ANTICIPO_PROMEMORIA)
    return ora if ora > adesso else None
