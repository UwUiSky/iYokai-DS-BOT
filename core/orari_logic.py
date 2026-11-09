"""
core/orari_logic.py
===================
Trova gli orari scritti in un testo (18:30, 6pm, 7:15 am) e li riscrive come timestamp di Discord, che
ognuno vede nel proprio fuso. Più i nomi dei fusi per il completamento (25 suggerimenti).
Funzioni coperte: catalogo #128 UTL-104 (D69, B6)
"""

from __future__ import annotations

import re
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

MAX_ORARI = 10
MAX_FUSO = 60

_ORARIO = re.compile(r"(?<![\d:.])(\d{1,2})(?::([0-5]\d))?\s?(am|pm|AM|PM)?(?![\d:])")


def trova_orari(testo: str) -> list[time]:
    """Gli orari del testo, nell'ordine e senza doppioni. Servono i due punti oppure am/pm: «18» da solo no."""
    trovati: list[time] = []
    for m in _ORARIO.finditer(testo or ""):
        ora, minuti, suffisso = int(m[1]), int(m[2] or 0), (m[3] or "").lower()
        if m[2] is None and not suffisso:
            continue
        if suffisso:
            if not 1 <= ora <= 12:
                continue
            ora = ora % 12 + (12 if suffisso == "pm" else 0)
        elif ora > 23:
            continue
        t = time(ora, minuti)
        if t not in trovati:
            trovati.append(t)
    return trovati[:MAX_ORARI]


def fuso_da_nome(nome: str | None, ripiego: str) -> ZoneInfo:
    try:
        return ZoneInfo(nome) if nome else ZoneInfo(ripiego)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo(ripiego)


def fuso_esiste(nome: str) -> bool:
    return nome in _nomi_fusi()


def timestamp_di(orario: time, fuso: ZoneInfo, adesso: datetime) -> int:
    """L'orario di oggi (data di `adesso` nel fuso) come secondi Unix."""
    oggi = adesso.astimezone(fuso).date()
    return int(datetime.combine(oggi, orario, tzinfo=fuso).astimezone(timezone.utc).timestamp())


def righe_orari(testo: str, fuso: ZoneInfo, adesso: datetime) -> list[str]:
    """«18:30 → <t:…:t> (<t:…:R>)» per ogni orario trovato."""
    return [
        f"`{o:%H:%M}` → <t:{(ts := timestamp_di(o, fuso, adesso))}:t> (<t:{ts}:R>)"
        for o in trova_orari(testo)
    ]


def _nomi_fusi() -> list[str]:
    return sorted(n for n in available_timezones() if "/" in n and not n.startswith(("Etc/", "SystemV/", "posix", "right")))


def cerca_fusi(testo: str, massimo: int = 25) -> list[str]:
    t = testo.strip().casefold().replace(" ", "_")
    return [n for n in _nomi_fusi() if t in n.casefold()][:massimo]
