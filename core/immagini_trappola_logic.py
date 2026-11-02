"""
core/immagini_trappola_logic.py
===============================
Regole della libreria delle immagini trappola (D62, come D39), in logica pura: stati, soglia dei
proprietari diversi, impronte, confronto per distanza. Una segnalazione e' «candidata» e vale solo nei
server che l'hanno fatta; con 3 proprietari diversi (server con almeno 25 membri) diventa «condivisa»
e vale ovunque; solo l'owner del bot la rende «approvata», cioe' certa. Una «rifiutata» non vale mai.
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.immagini_impronte import distanza, esito_distanza
from core.odio_libreria_logic import MIN_MEMBRI_PER_CONTARE, SOGLIA_SERVER  # noqa: F401  (le stesse soglie di D39)

CANDIDATA = "candidata"
CONDIVISA = "condivisa"
APPROVATA = "approvata"
RIFIUTATA = "rifiutata"
STATI = (CANDIDATA, CONDIVISA, APPROVATA, RIFIUTATA)
STATI_GLOBALI = (CONDIVISA, APPROVATA)

MAX_CANDIDATE_PER_SERVER = 200
MAX_MOTIVO = 200
MIN_PREFISSO = 6
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_PREFISSO = re.compile(r"^[0-9a-f]{%d,64}$" % MIN_PREFISSO)


@dataclass(frozen=True)
class Voce:
    sha256: str
    dhash: int | None
    stato: str
    motivo: str = ""


@dataclass(frozen=True)
class Trovata:
    voce: Voce
    distanza: int
    tipo: str  # uguale | simile


def sha_valido(valore) -> str | None:
    if not isinstance(valore, str):
        return None
    valore = valore.strip().lower()
    return valore if _HEX64.fullmatch(valore) else None


def prefisso_valido(valore) -> str | None:
    if not isinstance(valore, str):
        return None
    valore = valore.strip().lower()
    return valore if _HEX_PREFISSO.fullmatch(valore) else None


def dhash_a_database(valore: int | None) -> int | None:
    """Da 64 bit senza segno al BIGINT con segno di PostgreSQL."""
    if valore is None:
        return None
    return valore - 2**64 if valore >= 2**63 else valore


def dhash_dal_database(valore: int | None) -> int | None:
    if valore is None:
        return None
    return valore + 2**64 if valore < 0 else valore


def stato_dopo_segnalazione(stato: str, proprietari_diversi: int) -> str:
    if stato == CANDIDATA and proprietari_diversi >= SOGLIA_SERVER:
        return CONDIVISA
    return stato


def verdetto_di(stato: str) -> str | None:
    """`malevola` per le certe e le condivise, `sospetta` per le candidate, niente per le rifiutate."""
    if stato in STATI_GLOBALI:
        return "malevola"
    return "sospetta" if stato == CANDIDATA else None


def trova_per_impronta(dhash: int, voci: list[Voce]) -> Trovata | None:
    """La voce con l'impronta piu' vicina, se uguale (<= 4 bit) o simile (<= 8). Le voci senza impronta non contano."""
    migliore: Trovata | None = None
    for v in voci:
        if v.dhash is None:
            continue
        d = distanza(dhash, v.dhash)
        tipo = esito_distanza(d)
        if tipo != "diversa" and (migliore is None or d < migliore.distanza):
            migliore = Trovata(v, d, tipo)
    return migliore
