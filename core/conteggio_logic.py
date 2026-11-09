"""
core/conteggio_logic.py
=======================
Gioco del conteggio, parte pura (D69 B14-B15): leggere il numero scritto in decimale, binario, numeri romani
o in lettere (italiano, fino a 9.999), con filtro «solo numero» o «numero e poi testo»; scrivere un numero nel modo
del canale; trovare i traguardi raggiunti; leggere i punteggi da importare (CSV o JSON).
Funzioni coperte: catalogo UTL-187, 189, 191, 192
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass

MODI = ("decimale", "binario", "romani", "lettere")
FILTRI = ("solo_numero", "con_testo")
MAX_CANALI = 10
MAX_TRAGUARDI_PER_CANALE = 25
MAX_AVVISI_PER_UTENTE = 5
MAX_MESSAGGIO_TRAGUARDO = 300
MAX_PUNIZIONE_MINUTI = 1440
MAX_NUMERO = {"decimale": 999_999_999, "binario": 2**30 - 1, "romani": 3999, "lettere": 9999}

_UNITA = ["", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici", "dodici",
          "tredici", "quattordici", "quindici", "sedici", "diciassette", "diciotto", "diciannove"]
_DECINE = ["", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta"]
_ROMANI = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
           (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
_VALIDO_ROMANO = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def _sotto_cento(n: int) -> str:
    if n < 20:
        return _UNITA[n]
    d, u = divmod(n, 10)
    base = _DECINE[d]
    if u in (1, 8):
        base = base[:-1]  # ventuno, ventotto
    return base + (_UNITA[u] if u != 3 else "tré") if u else base


def _sotto_mille(n: int) -> str:
    c, resto = divmod(n, 100)
    testo = ""
    if c:
        testo = "cento" if c == 1 else _UNITA[c] + "cento"
        if resto // 10 == 8:
            testo = testo[:-1]  # centottanta
    return testo + _sotto_cento(resto)


def a_lettere(n: int) -> str:
    """1 -> uno, 21 -> ventuno, 100 -> cento, 2025 -> duemilaventicinque. Da 1 a 9.999."""
    if not 1 <= n <= 9999:
        raise ValueError("fuori misura")
    migliaia, resto = divmod(n, 1000)
    testo = ""
    if migliaia:
        testo = "mille" if migliaia == 1 else _UNITA[migliaia] + "mila"
    return testo + _sotto_mille(resto)


_DA_LETTERE: dict[str, int] = {}


def _tabella_lettere() -> dict[str, int]:
    if not _DA_LETTERE:
        for n in range(1, 10000):
            _DA_LETTERE[a_lettere(n)] = n
            _DA_LETTERE.setdefault(a_lettere(n).replace("tré", "tre"), n)  # ventitré o ventitre
    return _DA_LETTERE


def a_romano(n: int) -> str:
    if not 1 <= n <= 3999:
        raise ValueError("fuori misura")
    testo = ""
    for valore, simbolo in _ROMANI:
        while n >= valore:
            testo += simbolo
            n -= valore
    return testo


def da_romano(testo: str) -> int | None:
    t = testo.upper()
    if not t or not _VALIDO_ROMANO.match(t):
        return None
    n = 0
    resto = t
    for valore, simbolo in _ROMANI:
        while resto.startswith(simbolo):
            n += valore
            resto = resto[len(simbolo):]
    return n or None


def scrivi_numero(n: int, modo: str) -> str:
    """Il numero scritto nel modo del canale (per i messaggi del bot)."""
    if modo == "binario":
        return format(n, "b")
    if modo == "romani":
        return a_romano(n) if 1 <= n <= 3999 else str(n)
    if modo == "lettere":
        return a_lettere(n) if 1 <= n <= 9999 else str(n)
    return str(n)


def leggi_numero(testo: str, modo: str = "decimale", filtro: str = "solo_numero") -> int | None:
    """Il numero scritto in un messaggio nel modo del canale, o None (è chiacchiera)."""
    pulito = (testo or "").strip()
    if not pulito:
        return None
    if filtro == "con_testo":
        pulito = pulito.split(None, 1)[0]
    elif len(pulito.split()) != 1:
        return None
    if modo == "decimale":
        if not pulito.isascii() or not pulito.isdigit() or len(pulito) > 9:
            return None
        return int(pulito)
    if modo == "binario":
        if not set(pulito) <= {"0", "1"} or len(pulito) > 30:
            return None
        return int(pulito, 2)
    if modo == "romani":
        return da_romano(pulito)
    if modo == "lettere":
        return _tabella_lettere().get(pulito.lower())
    return None


@dataclass(frozen=True)
class Traguardo:
    id: int
    numero: int | None  # un numero preciso
    ogni: int | None  # oppure ogni tanti numeri
    ruolo_id: int | None
    messaggio: str | None


def traguardi_raggiunti(numero: int, traguardi: list[Traguardo]) -> list[Traguardo]:
    """I traguardi toccati da questo numero (uno preciso, oppure un multiplo)."""
    return [t for t in traguardi if (t.numero is not None and t.numero == numero) or (t.ogni and numero % t.ogni == 0)]


def tempo_di_blocco_valido(minuti: int) -> bool:
    return 0 <= minuti <= MAX_PUNIZIONE_MINUTI


MAX_BYTE_IMPORT = 1024 * 1024
MAX_RIGHE_IMPORT = 5000
MAX_PUNTI_IMPORT = 1_000_000


class ImportErrato(ValueError):
    """Il file da importare non va bene; il testo è la chiave del catalogo."""


def leggi_importazione(dati: bytes, nome_file: str) -> list[tuple[int, int, int]]:
    """Punteggi da un file CSV (user_id,giusti,sbagliati) o JSON (lista di oggetti, o {user_id: giusti}).
    Ritorna [(user_id, giusti, sbagliati)]. ImportErrato se il file non si legge o è troppo grande."""
    if len(dati) > MAX_BYTE_IMPORT:
        raise ImportErrato("conteggio_import_troppo_grande")
    try:
        testo = dati.decode("utf-8-sig")
        if nome_file.lower().endswith(".json"):
            grezzo = json.loads(testo)
            if isinstance(grezzo, dict):
                grezzo = [{"user_id": k, "giusti": v} for k, v in grezzo.items()]
            righe = [(r["user_id"], r.get("giusti", 0), r.get("sbagliati", 0)) for r in grezzo]
        else:
            righe = [
                (r["user_id"], r.get("giusti") or 0, r.get("sbagliati") or 0)
                for r in csv.DictReader(io.StringIO(testo))
            ]
        trovati = {}
        for utente, giusti, sbagliati in righe:
            utente, giusti, sbagliati = int(utente), int(giusti), int(sbagliati)
            if utente <= 0 or not (0 <= giusti <= MAX_PUNTI_IMPORT) or not (0 <= sbagliati <= MAX_PUNTI_IMPORT):
                raise ValueError
            trovati[utente] = (utente, giusti, sbagliati)
    except (ValueError, KeyError, TypeError, AttributeError, csv.Error, UnicodeDecodeError):
        raise ImportErrato("conteggio_import_illeggibile") from None
    if not trovati:
        raise ImportErrato("conteggio_import_vuoto")
    if len(trovati) > MAX_RIGHE_IMPORT:
        raise ImportErrato("conteggio_import_troppe_righe")
    return list(trovati.values())
