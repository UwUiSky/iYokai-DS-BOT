"""
core/rischio_logic.py
=====================
Regole pure dei guadagni a rischio: colpo (ECO-030/032), furto (ECO-031), elemosina (ECO-040),
cerca (ECO-041) e scala dei lavori (ECO-029). Il caso arriva da fuori (`rng`), così ogni esito
si prova con un seme fisso. Nessuna moneta nasce da un importo negativo o zero.
Funzioni coperte: ECO-029, ECO-030, ECO-031, ECO-032, ECO-040, ECO-041
"""

from __future__ import annotations

import random
from dataclasses import dataclass

MAX_FURTO = 5000  # tetto assoluto a un solo furto
PAUSA_COLPO = 2 * 3600
PAUSA_FURTO = 3600
PROTEZIONE_VITTIMA = 3600  # chi è stato derubato non lo è di nuovo per un'ora
PAUSA_ELEMOSINA = 600
PAUSA_CERCA = 1800
SALDO_MINIMO_FURTO = 50  # chi ha meno contanti non si deruba (né deruba)

# ECO-041: luogo -> (probabilità di trovare qualcosa in %, minimo, massimo)
LUOGHI = {
    "strada": (70, 5, 20),
    "cestino": (50, 10, 40),
    "divano": (25, 30, 100),
}

# ECO-029: lavoro -> (nome, turni per arrivarci, moltiplicatore in %)
LAVORI = (
    ("stagista", 0, 100),
    ("commesso", 10, 130),
    ("tecnico", 30, 170),
    ("responsabile", 70, 220),
    ("direttore", 150, 300),
)


@dataclass(frozen=True)
class EsitoColpo:
    riuscito: bool
    importo: int  # monete vinte (> 0) o multa chiesta (> 0): il segno lo dà `riuscito`


def lavoro_per_turni(turni: int) -> tuple[str, int, int]:
    """ECO-029: (nome, indice, moltiplicatore %) del lavoro raggiunto con tanti turni."""
    scelto = 0
    for indice, (_, soglia, _) in enumerate(LAVORI):
        if turni >= soglia:
            scelto = indice
    return LAVORI[scelto][0], scelto, LAVORI[scelto][2]


def turni_alla_promozione(turni: int) -> int | None:
    """Turni che mancano al lavoro dopo; None se si è già al massimo."""
    _, indice, _ = lavoro_per_turni(turni)
    return None if indice + 1 >= len(LAVORI) else LAVORI[indice + 1][1] - turni


def paga_con_lavoro(paga: int, moltiplicatore: int) -> int:
    return max(0, paga) * moltiplicatore // 100


def gioca_colpo(
    rng: random.Random, successo_pct: int, work_min: int, work_max: int, contanti: int, moltiplicatori: tuple[int, int] = (2, 4)
) -> EsitoColpo:
    """
    ECO-030/032: paga alta (da 2 a 4 volte il lavoro) se riesce, multa (metà del premio che sarebbe stato)
    se fallisce. La multa non supera i contanti: il saldo non scende sotto zero.
    """
    alto = max(work_min, work_max)
    premio = rng.randint(max(1, work_min) * moltiplicatori[0], max(1, alto) * moltiplicatori[1])
    if rng.randint(1, 100) <= successo_pct:
        return EsitoColpo(True, premio)
    return EsitoColpo(False, min(max(0, contanti), max(1, premio // 2)))


def importo_furto(contanti_vittima: int, percentuale: int) -> int:
    """ECO-031: la quota rubabile (almeno 1, mai oltre MAX_FURTO né oltre i contanti della vittima)."""
    if contanti_vittima < SALDO_MINIMO_FURTO:
        return 0
    return min(MAX_FURTO, contanti_vittima, max(1, contanti_vittima * percentuale // 100))


def multa_furto(importo: int, contanti_ladro: int) -> int:
    """Se il furto fallisce il ladro paga la metà dell'importo (non più dei suoi contanti) alla vittima."""
    return min(max(0, contanti_ladro), importo // 2)


def elemosina(rng: random.Random) -> int:
    """ECO-040: 0 (a volte niente) oppure da 1 a 10 monete."""
    return 0 if rng.randint(1, 100) <= 25 else rng.randint(1, 10)


def cerca(rng: random.Random, luogo: str) -> int:
    """ECO-041: monete trovate in un luogo (0 se non si trova niente)."""
    if luogo not in LUOGHI:
        raise ValueError(f"Luogo sconosciuto: {luogo}")
    probabilita, minimo, massimo = LUOGHI[luogo]
    return rng.randint(minimo, massimo) if rng.randint(1, 100) <= probabilita else 0
