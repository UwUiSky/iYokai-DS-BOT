"""
core/ai_pannello_logic.py
=========================
Dati per le pagine AI del pannello web: righe di «Uso dell'AI» dal registro dei dati e lettura sicura dei campi dei
moduli. Nessun accesso a Discord né alla rete.
Funzioni coperte: SPEC §25.91, §25.93 (AI-R-098, AI-R-100)
"""

from __future__ import annotations

from dataclasses import dataclass

from core.data_registry import REGISTRO


@dataclass(frozen=True)
class RigaUso:
    nome: str
    cosa: str
    quanto: str
    chi: str


def _quanto(t) -> str:
    if t.scadenza is not None:
        return f"{t.scadenza.giorni} giorni"
    return "finché serve alla funzione" if t.server == "cancella" else "conservato"


def _chi(t) -> str:
    if t.utente == "cancella":
        return "della persona, si cancella a richiesta"
    if t.utente == "anonimizza":
        return "della persona, resa anonima a richiesta"
    return "del server" if t.colonna_server else "non personale"


def righe_uso() -> list[RigaUso]:
    """Le tabelle dell'AI (nome che inizia con `ai_`) con cosa tengono, per quanto e di chi sono."""
    return [RigaUso(t.nome, t.descrizione, _quanto(t), _chi(t)) for t in REGISTRO if t.nome.startswith("ai_")]


def numeri(testo: object) -> list[int]:
    """Gli id scritti nei campi del modulo (solo cifre, al massimo 20)."""
    esito: list[int] = []
    for pezzo in (testo if isinstance(testo, list) else [testo]):
        s = str(pezzo)
        if s.isascii() and s.isdigit() and len(s) <= 20:
            esito.append(int(s))
    return esito
