"""
core/mondo_logic.py
===================
Regole pure di casa, diretta, fattoria, personaggi, avventure e borsa finta. Contenuti da file del repository
(`data/personaggi_it.json`, `data/avventure_it.json`), il caso arriva da fuori.
Funzioni coperte: ECO-018, ECO-045, ECO-083, ECO-084, ECO-085, ECO-087, ECO-142, ECO-146, ECO-147
"""

from __future__ import annotations

import json
import pathlib
import random
from datetime import date, datetime, timedelta

DATI = pathlib.Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------- casa (ECO-087): mobile -> (gettoni, emoji, posto 0-11 nella stanza 4x3)
MOBILI = {
    "letto": (6, "🛏️", 0), "scrivania": (4, "🗄️", 1), "lampada": (2, "🏮", 2), "finestra": (3, "🪟", 3),
    "tatami": (3, "🟫", 4), "tavolino": (2, "🪑", 5), "pianta": (1, "🪴", 6), "libreria": (5, "📚", 7),
    "tv": (8, "📺", 8), "gatto": (5, "🐈", 9), "bonsai": (4, "🌳", 10), "specchio": (3, "🪞", 11),
}
COLONNE_CASA = 4


def disegna_casa(posseduti: set[str]) -> str:
    celle = ["⬛"] * 12
    for nome, (_, emoji, posto) in MOBILI.items():
        if nome in posseduti:
            celle[posto] = emoji
    return "\n".join("".join(celle[r * COLONNE_CASA:(r + 1) * COLONNE_CASA]) for r in range(3))


# ---------------------------------------------------------------- diretta (ECO-045)
def serie_diretta(serie: int, ultimo: date | None, oggi: date) -> int | None:
    """La nuova serie, o None se oggi è già stata fatta. Un giorno saltato la riporta a 1."""
    if ultimo == oggi:
        return None
    return serie + 1 if ultimo is not None and ultimo == oggi - timedelta(days=1) else 1


def paga_diretta(serie: int) -> int:
    return 30 + 5 * min(max(serie, 1) - 1, 20)


# ---------------------------------------------------------------- fattoria (ECO-146): coltura -> (costo, ore, resa)
COLTURE = {"fiore": (5, 1, 9), "grano": (10, 2, 18), "zucca": (30, 6, 55)}
POSTI_FATTORIA = 3


def pronto(piantato: datetime, adesso: datetime, coltura: str) -> bool:
    return adesso >= piantato + timedelta(hours=COLTURE[coltura][1])


# ---------------------------------------------------------------- personaggi (ECO-142) e avventure (ECO-147)
_PERS: list[dict] | None = None
_AVV: dict | None = None


def personaggi() -> list[dict]:
    global _PERS
    if _PERS is None:
        _PERS = [p for p in json.loads((DATI / "personaggi_it.json").read_text(encoding="utf-8"))["personaggi"] if 0 <= p["g"] < len(p["r"])]
    return _PERS


def avventura() -> dict:
    global _AVV
    if _AVV is None:
        _AVV = json.loads((DATI / "avventure_it.json").read_text(encoding="utf-8"))
    return _AVV


# ---------------------------------------------------------------- borsa finta (ECO-084, 085)
SIMBOLI = {"KITSU": 100, "TANUK": 60, "YOKAI": 250, "SAKUR": 40, "ONIGI": 150}
PASSO_BORSA_S = 3600
PASSI_MASSIMI = 24
COMMISSIONE_PCT = 3
MAX_QUOTE_PER_TITOLO = 1000
MAX_ORDINI = 5


def passo_prezzo(prezzo: int, base: int, rng: random.Random) -> int:
    """Un'ora di borsa: ±5% a caso, mai sotto metà e mai sopra il doppio del prezzo base."""
    nuovo = round(prezzo * (1 + rng.uniform(-0.05, 0.05)))
    return min(max(nuovo, base // 2), base * 2)


def prezzo_dopo(prezzo: int, base: int, passi: int, rng: random.Random) -> int:
    for _ in range(min(max(passi, 0), PASSI_MASSIMI)):
        prezzo = passo_prezzo(prezzo, base, rng)
    return prezzo


def ordine_scatta(lato: str, prezzo: int, soglia: int) -> bool:
    return prezzo <= soglia if lato == "compra" else prezzo >= soglia


def costo_con_commissione(prezzo: int, quote: int) -> int:
    return prezzo * quote * (100 + COMMISSIONE_PCT) // 100 + (1 if prezzo * quote * (100 + COMMISSIONE_PCT) % 100 else 0)


def ricavo_con_commissione(prezzo: int, quote: int) -> int:
    return prezzo * quote * (100 - COMMISSIONE_PCT) // 100
