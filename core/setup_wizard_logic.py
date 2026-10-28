"""
core/setup_wizard_logic.py
==========================
Logica pura della configurazione guidata (`/admin setup wizard`): quali passi
ci sono e quali moduli sono cambiati. Nessuna dipendenza da Discord o dal database.
Funzioni coperte: SPEC §2.2, M 10.14 (#66)
"""

from __future__ import annotations

from dataclasses import dataclass

# Un menu di Discord tiene al massimo 25 opzioni (LIMITI.md, lista di controllo).
MAX_MODULI_PER_PASSO = 25

TIPO_RUOLI = "ruoli"
TIPO_MODULI = "moduli"


def clamp_step(index: int, total_steps: int) -> int:
    """Mantiene l'indice dello step dentro i limiti validi [0, total_steps - 1]."""
    if total_steps <= 0:
        raise ValueError("total_steps deve essere positivo.")
    return max(0, min(index, total_steps - 1))


def next_step(current: int, total_steps: int) -> int:
    return clamp_step(current + 1, total_steps)


def previous_step(current: int, total_steps: int) -> int:
    return clamp_step(current - 1, total_steps)


def is_last_step(current: int, total_steps: int) -> bool:
    return current >= total_steps - 1


@dataclass(frozen=True)
class Passo:
    """Un passo del wizard: i ruoli del bot, oppure i moduli di una categoria (o una parte)."""

    tipo: str
    categoria: str | None = None
    nomi: tuple[str, ...] = ()
    parte: int = 1
    parti: int = 1


def costruisci_passi(
    moduli_per_categoria: dict[str, list[str]],
    ordine_categorie: tuple[str, ...],
    max_per_passo: int = MAX_MODULI_PER_PASSO,
) -> list[Passo]:
    """
    Primo passo: i ruoli. Poi un passo per ogni categoria che ha moduli, nell'ordine dato.
    Una categoria con più di `max_per_passo` moduli si divide in più passi.
    Le categorie fuori dall'ordine dato vanno in coda, in ordine alfabetico.
    """
    passi = [Passo(tipo=TIPO_RUOLI)]
    resto = sorted(c for c in moduli_per_categoria if c not in ordine_categorie)
    for categoria in (*ordine_categorie, *resto):
        nomi = moduli_per_categoria.get(categoria) or []
        if not nomi:
            continue
        pezzi = [nomi[i:i + max_per_passo] for i in range(0, len(nomi), max_per_passo)]
        for numero, pezzo in enumerate(pezzi, start=1):
            passi.append(
                Passo(
                    tipo=TIPO_MODULI,
                    categoria=categoria,
                    nomi=tuple(pezzo),
                    parte=numero,
                    parti=len(pezzi),
                )
            )
    return passi


def moduli_da_scrivere(iniziale: dict[str, bool], scelto: dict[str, bool]) -> list[tuple[str, bool]]:
    """Solo i moduli il cui stato è davvero cambiato (lo storico non si riempie di rumore)."""
    return [(nome, attivo) for nome, attivo in scelto.items() if iniziale.get(nome) != attivo]
