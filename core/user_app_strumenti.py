"""
core/user_app_strumenti.py
==========================
Strumenti personali di iYokai App (SPEC §B.4): calcolatrice, conversioni, fusi orari, colori e codice QR.
Funzioni semplici, senza Discord e senza database. Ogni errore è `ErroreStrumento` con la chiave del
messaggio nel catalogo delle lingue.
Funzioni coperte: SPEC §B.4 (NF-36, #107)
Dipende da: segno (codice QR)
"""

from __future__ import annotations

import ast
import colorsys
import io
import math
import operator
import re
from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

MAX_ESPRESSIONE = 100
MAX_TESTO_QR = 300
MAX_ZONE_PROPOSTE = 25


class ErroreStrumento(ValueError):
    """`chiave`: la chiave del messaggio per l'utente (locales/it.json)."""

    def __init__(self, chiave: str) -> None:
        super().__init__(chiave)
        self.chiave = chiave


# ---------------------------------------------------------------- calcolatrice
_BINARI = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARI = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNZIONI = {"sqrt": math.sqrt, "abs": abs, "round": round}
_COSTANTI = {"pi": math.pi, "e": math.e}
_LIMITE = 1e15


def _valuta(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
        return n.value
    if isinstance(n, ast.Name) and n.id in _COSTANTI:
        return _COSTANTI[n.id]
    if isinstance(n, ast.UnaryOp) and type(n.op) in _UNARI:
        return _UNARI[type(n.op)](_valuta(n.operand))
    if isinstance(n, ast.BinOp) and type(n.op) in _BINARI:
        a, b = _valuta(n.left), _valuta(n.right)
        if isinstance(n.op, ast.Pow) and (abs(b) > 100 or abs(a) > _LIMITE):
            raise ErroreStrumento("app_calc_troppo_grande")
        return _BINARI[type(n.op)](a, b)
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNZIONI and not n.keywords:
        if not 1 <= len(n.args) <= (2 if n.func.id == "round" else 1):
            raise ErroreStrumento("app_calc_non_valida")
        return _FUNZIONI[n.func.id](*(_valuta(a) for a in n.args))
    raise ErroreStrumento("app_calc_non_valida")


def calcola(espressione: str) -> str:
    """Il risultato di un'espressione con + - * / // % ** ( ), sqrt, abs, round, pi, e. Mai `eval`."""
    testo = (espressione or "").strip().replace(",", ".").replace("^", "**")
    if not testo or len(testo) > MAX_ESPRESSIONE:
        raise ErroreStrumento("app_calc_non_valida")
    try:
        valore = _valuta(ast.parse(testo, mode="eval").body)
    except ErroreStrumento:
        raise
    except ZeroDivisionError:
        raise ErroreStrumento("app_calc_divisione_zero") from None
    except (SyntaxError, ValueError, TypeError, OverflowError, RecursionError, MemoryError):
        raise ErroreStrumento("app_calc_non_valida") from None
    if isinstance(valore, complex) or (isinstance(valore, float) and not math.isfinite(valore)) or abs(valore) > _LIMITE * 1e10:
        raise ErroreStrumento("app_calc_troppo_grande")
    if isinstance(valore, float) and valore.is_integer() and abs(valore) < 1e15:
        return str(int(valore))
    return str(valore) if isinstance(valore, int) else format(valore, ".10g")


# ---------------------------------------------------------------- conversioni
# categoria -> {unità: fattore verso l'unità base}
_UNITA: dict[str, dict[str, float]] = {
    "lunghezza": {"mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0, "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344},
    "massa": {"mg": 1e-6, "g": 0.001, "kg": 1.0, "t": 1000.0, "oz": 0.028349523125, "lb": 0.45359237},
    "volume": {"ml": 0.001, "cl": 0.01, "l": 1.0, "floz": 0.0295735295625, "gal": 3.785411784},
    "velocita": {"m/s": 1.0, "km/h": 1 / 3.6, "mph": 0.44704, "kn": 0.514444},
    "dati": {"b": 1.0, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kib": 1024.0, "mib": 1024.0**2, "gib": 1024.0**3},
}
_TEMPERATURE = ("c", "f", "k")
UNITA_ELENCO = tuple(sorted({u for d in _UNITA.values() for u in d} | set(_TEMPERATURE)))


def _in_celsius(v: float, da: str) -> float:
    return v if da == "c" else (v - 32) * 5 / 9 if da == "f" else v - 273.15


def _da_celsius(c: float, a: str) -> float:
    return c if a == "c" else c * 9 / 5 + 32 if a == "f" else c + 273.15


def converti(valore: float, da: str, a: str) -> float:
    """Converte tra unità della stessa categoria (lunghezza, massa, volume, velocità, dati, temperatura)."""
    da, a = da.strip().lower(), a.strip().lower()
    if not math.isfinite(valore):
        raise ErroreStrumento("app_conv_valore")
    if da in _TEMPERATURE and a in _TEMPERATURE:
        return _da_celsius(_in_celsius(valore, da), a)
    for tabella in _UNITA.values():
        if da in tabella and a in tabella:
            return valore * tabella[da] / tabella[a]
    noto = da in UNITA_ELENCO and a in UNITA_ELENCO
    raise ErroreStrumento("app_conv_categorie" if noto else "app_conv_unita")


def formatta_numero(v: float) -> str:
    return format(v, ".6g") if abs(v) < 1e12 else format(v, ".6e")


# ---------------------------------------------------------------- fusi orari
def zona(nome: str) -> ZoneInfo:
    try:
        if not re.fullmatch(r"[A-Za-z0-9_+\-/]{1,40}", nome or ""):
            raise ZoneInfoNotFoundError(nome)
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ErroreStrumento("app_fuso_sconosciuto") from None


def zone_che_iniziano(testo: str, massimo: int = MAX_ZONE_PROPOSTE) -> list[str]:
    """Nomi di fusi (es. Europe/Rome) che contengono `testo`, per il completamento."""
    cerca = (testo or "").lower().replace(" ", "_")
    return [z for z in sorted(available_timezones()) if cerca in z.lower()][:massimo]


def converti_ora(ora: str | None, da: str, a: str, adesso: datetime | None = None) -> tuple[datetime, datetime]:
    """(ora nel fuso di partenza, ora nel fuso di arrivo). `ora` è HH:MM di oggi; senza, è adesso."""
    origine, destinazione = zona(da), zona(a)
    base = (adesso or datetime.now(timezone.utc)).astimezone(origine)
    if ora:
        m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", ora.strip())
        if m is None:
            raise ErroreStrumento("app_fuso_ora")
        base = datetime.combine(base.date(), time(int(m.group(1)), int(m.group(2))), tzinfo=origine)
    return base, base.astimezone(destinazione)


# ---------------------------------------------------------------- colori
@dataclass(frozen=True)
class Colore:
    r: int
    g: int
    b: int

    @property
    def hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @property
    def intero(self) -> int:
        return (self.r << 16) | (self.g << 8) | self.b

    @property
    def rgb(self) -> str:
        return f"rgb({self.r}, {self.g}, {self.b})"

    @property
    def hsl(self) -> str:
        h, l, s = colorsys.rgb_to_hls(self.r / 255, self.g / 255, self.b / 255)
        return f"hsl({round(h * 360)}, {round(s * 100)}%, {round(l * 100)}%)"


_HEX = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
_RGB = re.compile(r"(?:rgb\s*\()?\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*\)?")


def leggi_colore(testo: str) -> Colore:
    """Un colore da `#ff8800`, `f80`, `rgb(255,136,0)` o `255 136 0`."""
    t = (testo or "").strip()
    m = _HEX.fullmatch(t)
    if m:
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        return Colore(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = _RGB.fullmatch(t)
    if m and all(int(x) <= 255 for x in m.groups()):
        return Colore(*(int(x) for x in m.groups()))
    raise ErroreStrumento("app_colore_non_valido")


def immagine_colore(colore: Colore) -> bytes:
    """Un quadrato PNG 128x128 del colore."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (128, 128), (colore.r, colore.g, colore.b)).save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- codice QR
def qr_png(testo: str) -> bytes:
    """Il codice QR del testo come PNG (testo fino a 300 caratteri)."""
    import segno

    testo = (testo or "").strip()
    if not testo or len(testo) > MAX_TESTO_QR:
        raise ErroreStrumento("app_qr_testo")
    buf = io.BytesIO()
    segno.make(testo, error="m").save(buf, kind="png", scale=8, border=4)
    return buf.getvalue()
