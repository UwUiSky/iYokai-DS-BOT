"""
core/server_sync_logic.py
=========================
Sincronia tra due server dello stesso proprietario: cosa copiare quando
cambiano i ban o i ruoli di un membro. I ruoli passano per nome; quelli gestiti
da un'integrazione o sopra il ruolo del bot non si toccano.
Funzioni coperte: SPEC §11.16, §23 (NF-39)
"""

from __future__ import annotations

MAX_SINCRONIE_PER_SERVER = 5
MAX_MOTIVO = 512


def coppia(a: int, b: int) -> tuple[int, int]:
    """La coppia in ordine (guild_a < guild_b): una sola riga per due server."""
    return (a, b) if a < b else (b, a)


def stesso_proprietario(utente_id: int, *proprietari: int) -> bool:
    """Solo chi possiede entrambi i server può legarli."""
    return all(p == utente_id for p in proprietari)


def differenza_ruoli(prima: set[str], dopo: set[str]) -> tuple[set[str], set[str]]:
    """(aggiunti, tolti), per nome."""
    return dopo - prima, prima - dopo


def ruoli_applicabili(nomi: set[str], ruoli_destinazione, ruolo_alto_del_bot, permessi_sorgente=None) -> list:
    """
    I ruoli della destinazione con quei nomi che il bot può dare o togliere.
    Con `permessi_sorgente` (nome -> valore dei permessi nel server d'origine) un
    ruolo passa solo se non ha permessi in più di quello omonimo d'origine: un
    ruolo «Admin» creato senza permessi in un server non dà l'«Admin» vero dell'altro.
    """
    return [
        r for r in ruoli_destinazione
        if r.name in nomi and not r.is_default() and not r.managed and r < ruolo_alto_del_bot
        and (permessi_sorgente is None or r.permissions.value & ~permessi_sorgente.get(r.name, 0) == 0)
    ]


def motivo(nome_server: str, motivo_originale: str | None) -> str:
    testo = f"Sincronia da {nome_server}"
    if motivo_originale:
        testo += f": {motivo_originale}"
    return testo[:MAX_MOTIVO]
