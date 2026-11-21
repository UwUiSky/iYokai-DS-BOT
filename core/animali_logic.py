"""
core/animali_logic.py
=====================
Regole pure di animali (ECO-122, 123, 124, 130, 131) e pesca (ECO-132, 134, 138). Fame, pulizia e gioco calano col
tempo e si calcolano alla lettura (nessun lavoro in corso). Il caso arriva da fuori (`rng`).
Funzioni coperte: ECO-122, ECO-123, ECO-124, ECO-130, ECO-131, ECO-132, ECO-134
"""

from __future__ import annotations

import random
from datetime import datetime

# specie -> (prezzo, bonus % al lavoro, bonus % al premio periodico)
SPECIE = {
    "gatto": (300, 5, 0),
    "volpe": (800, 4, 6),
    "civetta": (500, 0, 8),
    "rana": (200, 3, 0),
}
MAX_NOME = 20
POSTI_BASE = 1
POSTI_EXTRA_MAX = 2
COSTO_POSTO = 1000
CALO_ORARIO = {"fame": 4, "igiene": 2, "gioco": 3}  # punti persi ogni ora
PAUSA_CURA = 3600
COSTO_CURA = {"fame": 5, "igiene": 0, "gioco": 0}
XP_CURA = 5
XP_PER_LIVELLO = 50
LIVELLO_MASSIMO = 10
SALUTE_MINIMA_BONUS = 30
PAUSA_ATTIVITA = 7200
ATTIVITA = ("riporto", "nuoto", "canto")


def valore_stato(ultima_cura: datetime, adesso: datetime, tipo: str) -> int:
    """Quanto è «pieno» (0-100) uno dei tre bisogni: 100 appena curato, cala ogni ora."""
    ore = max(0.0, (adesso - ultima_cura).total_seconds() / 3600)
    return max(0, 100 - int(ore * CALO_ORARIO[tipo]))


def salute(fame_at: datetime, igiene_at: datetime, gioco_at: datetime, adesso: datetime) -> int:
    """La media dei tre bisogni."""
    return (valore_stato(fame_at, adesso, "fame") + valore_stato(igiene_at, adesso, "igiene") + valore_stato(gioco_at, adesso, "gioco")) // 3


def livello(xp: int) -> int:
    return min(LIVELLO_MASSIMO, max(0, xp) // XP_PER_LIVELLO)


def nome_valido(nome: str) -> str:
    pulito = " ".join(nome.split())
    if not 1 <= len(pulito) <= MAX_NOME or any(c in pulito for c in "@#`*_~|<>[]"):
        raise ValueError(f"Il nome deve avere da 1 a {MAX_NOME} caratteri, senza simboli di formattazione o menzioni.")
    return pulito


def bonus_percentuale(animali: list[tuple[str, int, int]], tipo: str) -> int:
    """
    ECO-131: bonus % al lavoro o al premio dato dagli animali ben tenuti (salute >= 30), cresce del 10% a livello.
    `animali` = [(specie, salute, livello)]. Si sommano al massimo il migliore per tipo e mai più di 15%.
    """
    migliori = 0
    for specie, sal, liv in animali:
        if specie not in SPECIE or sal < SALUTE_MINIMA_BONUS:
            continue
        base = SPECIE[specie][1] if tipo == "lavoro" else SPECIE[specie][2]
        migliori = max(migliori, base * (10 + liv) // 10)
    return min(15, migliori)


def premio_attivita(rng: random.Random, liv: int) -> int:
    """ECO-130: monete di un'attività: da 5 a 15, più il livello."""
    return rng.randint(5, 15) + liv


def costo_posto(extra_attuali: int) -> int | None:
    if not 0 <= extra_attuali < POSTI_EXTRA_MAX:
        return None
    return COSTO_POSTO * (extra_attuali + 1)


# ---------------------------------------------------------------- pesca
# luogo -> [(specie, peso)] ; None = niente (stivale)
PESCI = {
    "sardina": (2, "🐟"), "carpa": (5, "🐟"), "trota": (10, "🐠"), "anguilla": (20, "🐍"), "luccio": (40, "🐊"), "koi dorato": (120, "✨"),
}
LUOGHI_PESCA = {
    "stagno": [(None, 30), ("sardina", 30), ("carpa", 25), ("trota", 12), ("luccio", 3)],
    "fiume": [(None, 25), ("sardina", 20), ("carpa", 20), ("trota", 20), ("anguilla", 10), ("luccio", 4), ("koi dorato", 1)],
    "mare": [(None, 20), ("sardina", 20), ("trota", 25), ("anguilla", 20), ("luccio", 12), ("koi dorato", 3)],
}
PAUSA_PESCA = 900
MAX_PESCI_DEPOSITO = 200


def pesca(rng: random.Random, luogo: str) -> str | None:
    """ECO-132: la specie pescata, o None."""
    if luogo not in LUOGHI_PESCA:
        raise ValueError(f"Luogo sconosciuto: {luogo}")
    tabella = LUOGHI_PESCA[luogo]
    punto = rng.randint(1, sum(p for _, p in tabella))
    for specie, peso in tabella:
        punto -= peso
        if punto <= 0:
            return specie
    raise AssertionError("pesi della pesca sbagliati")


def valore_atteso_pesca(luogo: str) -> float:
    tabella = LUOGHI_PESCA[luogo]
    totale = sum(p for _, p in tabella)
    return sum(PESCI[s][0] * p for s, p in tabella if s) / totale


def valore_pesci(quantita: dict[str, int]) -> int:
    """Quanto vale un deposito (prezzi fissi)."""
    return sum(PESCI[s][0] * n for s, n in quantita.items() if s in PESCI and n > 0)
