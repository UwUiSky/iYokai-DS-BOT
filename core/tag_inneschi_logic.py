"""
core/tag_inneschi_logic.py
==========================
Inneschi dei tag (B27): quando un tag parte da solo. Reazione, intervallo (minimo 10 minuti), orario (cron a 5 campi,
minimo 10 minuti tra due giri), bottone di un embed, ruolo dato o tolto. Leggere e controllare i valori, calcolare il giro
dopo, ore e giorni da saltare. Funzioni semplici, senza Discord e senza database.
Funzioni coperte: catalogo #128 UTL-047..050, 052, 054 (D69, B27)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from core.custom_command_logic import leggi_reazioni

TIPI = ("reazione", "intervallo", "orario", "bottone", "ruolo_dato", "ruolo_tolto")
TIPI_A_TEMPO = ("intervallo", "orario")
MAX_INNESCHI = 25
MIN_SECONDI = 600
MAX_INTERVALLO = 30 * 86400
MAX_VALORE = 100
MAX_ESCLUDI = 100
ROMA = ZoneInfo("Europe/Rome")
AZIONE_INNESCO = "tag_innesco"

_UNITA = {"m": 60, "min": 60, "h": 3600, "ore": 3600, "g": 86400, "d": 86400}
_GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
_CAMPI = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def leggi_intervallo(testo: str) -> int | None:
    """`30m`, `2h`, `1g`, `1h30m` -> secondi; None se non si capisce o è fuori da 10 minuti - 30 giorni."""
    resto = (testo or "").strip().casefold().replace(" ", "")
    totale = 0
    while resto:
        m = re.match(r"(\d{1,5})(min|ore|m|h|g|d)", resto)
        if not m:
            return None
        totale += int(m.group(1)) * _UNITA[m.group(2)]
        resto = resto[m.end():]
    return totale if MIN_SECONDI <= totale <= MAX_INTERVALLO else None


def _campo(testo: str, minimo: int, massimo: int) -> set[int] | None:
    fuori: set[int] = set()
    for parte in testo.split(","):
        base, barra, passo_testo = parte.partition("/")
        if barra and (not passo_testo.isdigit() or int(passo_testo) < 1):
            return None
        passo = int(passo_testo) if barra else 1
        if base == "*":
            a, b = minimo, massimo
        elif re.fullmatch(r"\d{1,2}-\d{1,2}", base):
            a, b = (int(x) for x in base.split("-"))
        elif re.fullmatch(r"\d{1,2}", base):
            a = int(base)
            b = massimo if barra else a
        else:
            return None
        if a < minimo or b > massimo or a > b:
            return None
        fuori.update(range(a, b + 1, passo))
    return fuori


def _campi_cron(testo: str):
    pezzi = (testo or "").split()
    if len(pezzi) != 5 or len(testo) > MAX_VALORE:
        return None
    insiemi = [_campo(p, lo, hi) for p, (lo, hi) in zip(pezzi, _CAMPI)]
    if any(i is None for i in insiemi):
        return None
    insiemi[4] = {x % 7 for x in insiemi[4]}  # 7 = domenica come 0
    return pezzi, insiemi


def leggi_cron(testo: str) -> str | None:
    """Il cron a 5 campi (minuto ora giorno mese giorno-settimana) con gli spazi a posto, o None."""
    letto = _campi_cron(testo)
    return " ".join(letto[0]) if letto else None


def prossimo_cron(cron: str, dopo: datetime) -> datetime | None:
    """Il primo istante dopo `dopo` (ora di Roma) che corrisponde al cron; None se non capita entro un anno."""
    letto = _campi_cron(cron)
    if letto is None:
        return None
    pezzi, (minuti, ore, giorni, mesi, settimana) = letto
    dopo = dopo.astimezone(ROMA) if dopo.tzinfo else dopo.replace(tzinfo=ROMA)
    t = dopo.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limite = t + timedelta(days=366)
    giorno_libero, settimana_libera = pezzi[2].startswith("*"), pezzi[4].startswith("*")

    def giorno_ok(x: datetime) -> bool:
        dom, sett = x.day in giorni, (x.weekday() + 1) % 7 in settimana
        if giorno_libero and settimana_libera:
            return True
        if settimana_libera:
            return dom
        if giorno_libero:
            return sett
        return dom or sett

    while t < limite:
        if t.month not in mesi:
            t = (t.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
        elif not giorno_ok(t):
            t = (t + timedelta(days=1)).replace(hour=0, minute=0)
        elif t.hour not in ore:
            t = (t + timedelta(hours=1)).replace(minute=0)
        elif t.minute not in minuti:
            t += timedelta(minutes=1)
        else:
            return t
    return None


def cron_troppo_fitto(cron: str) -> bool:
    """Vero se tra due giri passano meno di 10 minuti (si guardano i prossimi 12)."""
    t = datetime(2026, 1, 5, 0, 0, tzinfo=ROMA)
    precedente = None
    for _ in range(12):
        t = prossimo_cron(cron, t)
        if t is None:
            return False
        if precedente is not None and (t - precedente).total_seconds() < MIN_SECONDI:
            return True
        precedente = t
    return False


def leggi_escludi(testo: str) -> str | None:
    """Ore e giorni in cui l'innesco salta: `23-7 sab dom`. Vuoto = niente da saltare. None se non si capisce."""
    pezzi = (testo or "").replace(",", " ").split()
    if len(testo or "") > MAX_ESCLUDI:
        return None
    for p in pezzi:
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", p)
        if m:
            if not (0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 24) or m.group(1) == m.group(2):
                return None
        elif p.casefold() not in _GIORNI:
            return None
    return " ".join(p.casefold() for p in pezzi)


def escluso(escludi: str, quando: datetime) -> bool:
    """Vero se `quando` (ora di Roma) cade in un'ora o in un giorno da saltare."""
    quando = quando.astimezone(ROMA) if quando.tzinfo else quando.replace(tzinfo=ROMA)
    for p in (escludi or "").split():
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", p)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if (a <= quando.hour < b) if a < b else (quando.hour >= a or quando.hour < b):
                return True
        elif p == _GIORNI[quando.weekday()]:
            return True
    return False


def valida(tipo: str, valore: str) -> tuple[str | None, str | None]:
    """(valore pulito, None) oppure (None, chiave del testo d'errore)."""
    valore = (valore or "").strip()
    if tipo == "reazione":
        emoji = leggi_reazioni(valore)
        return (emoji[0].replace("️", ""), None) if emoji and len(emoji) == 1 else (None, "inn_reazione_non_valida")
    if tipo == "intervallo":
        return (valore.casefold().replace(" ", ""), None) if leggi_intervallo(valore) else (None, "inn_intervallo_non_valido")
    if tipo == "orario":
        cron = leggi_cron(valore)
        if cron is None or prossimo_cron(cron, datetime.now(timezone.utc)) is None:
            return None, "inn_orario_non_valido"
        return (None, "inn_orario_troppo_fitto") if cron_troppo_fitto(cron) else (cron, None)
    if tipo == "bottone":
        return (valore.casefold(), None) if re.fullmatch(r"[a-z0-9_-]{1,32}:\d{1,2}", valore.casefold()) else (None, "inn_bottone_non_valido")
    if tipo in ("ruolo_dato", "ruolo_tolto"):
        return (valore, None) if re.fullmatch(r"\d{15,20}", valore) else (None, "inn_ruolo_mancante")
    return None, "inn_tipo_non_valido"


def prossimo_giro(tipo: str, valore: str, dopo: datetime) -> datetime | None:
    """Quando riparte un innesco a tempo (in UTC); None se non ripartirà mai."""
    if tipo == "intervallo":
        secondi = leggi_intervallo(valore)
        return dopo + timedelta(seconds=secondi) if secondi else None
    if tipo == "orario":
        prossimo = prossimo_cron(valore, dopo)
        return prossimo.astimezone(timezone.utc) if prossimo else None
    return None


def stessa_emoji(a: str, b: str) -> bool:
    return a.replace("️", "") == b.replace("️", "")
