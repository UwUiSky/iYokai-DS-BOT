"""
core/programmati_logic.py
=========================
Messaggi programmati che si ripetono: ogni N tempo, a un'ora fissa del giorno, salto del prossimo giro e
«non ripetere se l'ultimo messaggio è già il nostro». Funzioni pure sulle date (UTC dentro, fuso fuori).
Funzioni coperte: catalogo #128 UTL-105, 106, 107, 108, 109 (D69, B5)
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MIN_RIPETI_SECONDI = 600  # almeno 10 minuti tra un messaggio e l'altro
MAX_SERIE_PER_SERVER = 25
SECONDI_GIORNO = 86400
SECONDI_PING_BREVE = 10
FUSO_PREDEFINITO = "Europe/Rome"

_ORA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def leggi_ora(testo: str) -> time:
    """«18:30» -> time(18, 30). ValueError con un messaggio per l'utente."""
    m = _ORA.match(testo.strip())
    if not m:
        raise ValueError("L'ora va scritta così: 18:30 (24 ore).")
    return time(int(m[1]), int(m[2]))


def fuso_valido(nome: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(nome or FUSO_PREDEFINITO)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo(FUSO_PREDEFINITO)


def errore_ripetizione(ripeti_secondi: int | None, ora: time | None) -> str | None:
    if ripeti_secondi is None:
        return None
    if ripeti_secondi < MIN_RIPETI_SECONDI:
        return "Il messaggio si può ripetere al massimo ogni 10 minuti."
    if ora is not None and ripeti_secondi % SECONDI_GIORNO:
        return "Con un'ora fissa la ripetizione è in giorni: 1d, 2d, 7d..."
    return None


def prima_ora_fissa(dopo: datetime, ora: time, fuso: ZoneInfo) -> datetime:
    """La prima volta in cui sull'orologio del `fuso` sono le `ora`, dopo `dopo` (UTC)."""
    locale = dopo.astimezone(fuso)
    candidato = datetime.combine(locale.date(), ora, tzinfo=fuso)
    if candidato <= locale:
        candidato = datetime.combine(locale.date() + timedelta(days=1), ora, tzinfo=fuso)
    return candidato.astimezone(timezone.utc)


def prossimo_giro(
    precedente: datetime, ripeti_secondi: int, adesso: datetime, ora: time | None = None, fuso: ZoneInfo | None = None
) -> datetime:
    """
    Il prossimo orario, sempre dopo `adesso`. Senza ora fissa si somma al giro precedente (niente deriva);
    con l'ora fissa si salta di N giorni sul calendario del fuso, così l'ora resta la stessa anche col cambio
    dell'ora legale. Se il bot è stato spento si saltano i giri persi, senza recuperarli.
    """
    if ora is None:
        n = max(1, int((adesso - precedente).total_seconds() // ripeti_secondi) + 1)
        return precedente + timedelta(seconds=ripeti_secondi * n)
    fuso = fuso or fuso_valido(None)
    giorni = max(1, ripeti_secondi // SECONDI_GIORNO)
    data = precedente.astimezone(fuso).date()
    while True:
        data += timedelta(days=giorni)
        candidato = datetime.combine(data, ora, tzinfo=fuso).astimezone(timezone.utc)
        if candidato > adesso:
            return candidato


def deve_saltare(salta_se_ultimo: bool, ultimo_id_canale: int | None, ultimo_id_nostro: int | None) -> bool:
    """Non ripetere un messaggio se l'ultimo del canale è ancora quello che avevamo mandato noi."""
    return bool(salta_se_ultimo and ultimo_id_nostro and ultimo_id_canale == ultimo_id_nostro)


def giro_di(payload: dict) -> int | None:
    v = payload.get("ripeti")
    return int(v) if isinstance(v, int) and v >= MIN_RIPETI_SECONDI else None
