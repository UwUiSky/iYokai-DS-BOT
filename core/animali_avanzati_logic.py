"""
core/animali_avanzati_logic.py
==============================
Regole pure di animali avanzati (sitter, lotte, incontri, adozioni) e pesca avanzata (abilità, perle, attrezzi,
pass stagionale, rete). Il caso arriva da fuori (`rng`); niente database.
Funzioni coperte: ECO-125, ECO-126, ECO-127, ECO-128, ECO-129, ECO-135, ECO-136, ECO-137, ECO-140
"""

from __future__ import annotations

import random
from datetime import date

from core.animali_logic import LUOGHI_PESCA, PAUSA_PESCA, PESCI

# ---------------------------------------------------------------- animali
COSTO_SITTER_GIORNO = 40
SITTER_GIORNI_MAX = 7
PAUSA_LOTTA = 3600
XP_VITTORIA, XP_SCONFITTA, XP_INCONTRO = 10, 3, 5
CHANCE_CUCCIOLO_PCT = 25
CODA_ADOZIONE_MAX = 20
NOME_CUCCIOLO = "Cucciolo"


def costo_sitter(giorni: int) -> int:
    if not 1 <= giorni <= SITTER_GIORNI_MAX:
        raise ValueError("Giorni non validi.")
    return COSTO_SITTER_GIORNO * giorni


def nasce_cucciolo(rng: random.Random) -> bool:
    return rng.randint(1, 100) <= CHANCE_CUCCIOLO_PCT


def specie_cucciolo(rng: random.Random, specie_a: str, specie_b: str) -> str:
    return rng.choice([specie_a, specie_b])


# ---------------------------------------------------------------- pesca
ABILITA = {"occhio": 2, "pazienza": 2, "capiente": 3, "mercante": 3}  # costo in punti abilità
CAPIENZA_BASE = 200
PERLE_ESCA = 5
PERLE_RETE = 30
PERLE_CANNA = (20, 40, 80)  # livello 1, 2, 3
CANNA_MAX = 3
RETE_PAUSA_S = 3600
RETE_LANCI_MAX = 12
SOGLIA_STAGIONE = 100
LIVELLI_STAGIONE = 10


def punti_abilita(pescati: int, specie_viste: int) -> int:
    """Le sfide: un punto ogni 20 pesci presi e uno per ogni specie trovata."""
    return max(0, pescati) // 20 + max(0, specie_viste)


def pausa_pesca(abilita: set[str], canna: int) -> int:
    pausa = PAUSA_PESCA * (8 if "pazienza" in abilita else 10) // 10
    return max(300, pausa - 60 * min(max(canna, 0), CANNA_MAX))


def capienza(abilita: set[str]) -> int:
    return CAPIENZA_BASE + (100 if "capiente" in abilita else 0)


def pesca_con(rng: random.Random, luogo: str, abilita: set[str], esca: bool) -> str | None:
    """Come `animali_logic.pesca`, ma «occhio» e l'esca tolgono peso al «niente»."""
    if luogo not in LUOGHI_PESCA:
        raise ValueError(f"Luogo sconosciuto: {luogo}")
    tabella = []
    for specie, peso in LUOGHI_PESCA[luogo]:
        if specie is None:
            peso = max(5, peso - (8 if "occhio" in abilita else 0))
            if esca:
                peso = max(3, peso // 2)
        tabella.append((specie, peso))
    punto = rng.randint(1, sum(p for _, p in tabella))
    for specie, peso in tabella:
        punto -= peso
        if punto <= 0:
            return specie
    raise AssertionError("pesi della pesca sbagliati")


def perle_per(specie: str) -> int:
    """Moneta dedicata ai soli attrezzi: una perla ogni 5 monete di valore, almeno una."""
    return max(1, PESCI[specie][0] // 5)


def bonus_vendita(abilita: set[str]) -> int:
    return 10 if "mercante" in abilita else 0


def stagione(giorno: date) -> str:
    return f"{giorno.year}-{giorno.month:02d}"


def livello_stagione(punti: int) -> int:
    return min(LIVELLI_STAGIONE, max(0, punti) // SOGLIA_STAGIONE)


def premio_stagione(livello: int) -> int:
    """Traccia gratuita: 20 monete per il livello 1, 40 per il 2... fino a 200."""
    return 20 * livello


def lanci_rete(secondi_passati: float) -> int:
    return min(RETE_LANCI_MAX, max(0, int(secondi_passati // RETE_PAUSA_S)))
