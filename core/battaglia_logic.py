"""
core/battaglia_logic.py
=======================
Regole pure della battaglia a turni tra due utenti (FUN-019): attacco, difesa e abilità. Senza Discord e senza
database; il caso entra da fuori (`rng`) così le prove sono ripetibili.
Funzioni coperte: FUN-019
"""

from __future__ import annotations

import random
from dataclasses import dataclass

PUNTI_VITA = 100
TURNI_MASSIMI = 16  # in tutto: oltre, vince chi ha più punti vita (a pari punti, pareggio)
TEMPO_TURNO = 40  # secondi: chi non agisce perde
RICARICA_ABILITA = 3  # turni propri tra un'abilità e la successiva
DANNO_ATTACCO = (8, 14)
DANNO_ABILITA = (18, 26)
CURA_DIFESA = 3
PROBABILITA_ABILITA_A_VUOTO = 25  # su 100

ATTACCO, DIFESA, ABILITA = "attacco", "difesa", "abilita"
AZIONI = (ATTACCO, DIFESA, ABILITA)


@dataclass
class Combattente:
    pv: int = PUNTI_VITA
    guardia: bool = False  # il prossimo colpo subito si dimezza
    ricarica: int = 0  # turni propri ancora da aspettare per l'abilità


@dataclass(frozen=True)
class Esito:
    azione: str
    danno: int = 0
    parato: bool = False
    mancato: bool = False
    curato: int = 0


def inizia_turno(c: Combattente) -> None:
    """All'inizio del turno di `c`: la guardia di prima finisce e la ricarica scende di uno."""
    c.guardia = False
    if c.ricarica > 0:
        c.ricarica -= 1


def puo_agire(c: Combattente, azione: str) -> bool:
    if azione not in AZIONI:
        return False
    return not (azione == ABILITA and c.ricarica > 0)


def esegui(chi: Combattente, altro: Combattente, azione: str, rng: random.Random | None = None) -> Esito:
    """Applica l'azione di `chi` contro `altro`. Solleva ValueError per un'azione non ammessa."""
    if not puo_agire(chi, azione):
        raise ValueError(azione)
    rng = rng or random.SystemRandom()
    if azione == DIFESA:
        prima = chi.pv
        chi.guardia = True
        chi.pv = min(PUNTI_VITA, chi.pv + CURA_DIFESA)
        return Esito(DIFESA, curato=chi.pv - prima)
    if azione == ABILITA:
        chi.ricarica = RICARICA_ABILITA
        if rng.randint(1, 100) <= PROBABILITA_ABILITA_A_VUOTO:
            return Esito(ABILITA, mancato=True)
        danno = rng.randint(*DANNO_ABILITA)
    else:
        danno = rng.randint(*DANNO_ATTACCO)
    parato = altro.guardia
    if parato:
        danno //= 2
        altro.guardia = False
    altro.pv = max(0, altro.pv - danno)
    return Esito(azione, danno=danno, parato=parato)


def vincitore(a: Combattente, b: Combattente, turni_fatti: int) -> int | None:
    """1 o 2 se la battaglia è finita (0 = pareggio dopo il limite dei turni), None se continua."""
    if a.pv <= 0 and b.pv <= 0:
        return 0
    if b.pv <= 0:
        return 1
    if a.pv <= 0:
        return 2
    if turni_fatti >= TURNI_MASSIMI:
        return 1 if a.pv > b.pv else 2 if b.pv > a.pv else 0
    return None


def barra(pv: int, larghezza: int = 10) -> str:
    pieni = max(0, min(larghezza, -(-pv * larghezza // PUNTI_VITA))) if pv > 0 else 0
    return "█" * pieni + "░" * (larghezza - pieni)
