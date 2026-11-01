"""
tests/support/percorsi.py
=========================
Aiuto per i test dei gruppi F7: l'elenco dei percorsi ("sottogruppo comando")
dei comandi registrati in un gruppo condiviso di core/command_groups.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from discord import app_commands

from core.command_groups import GRUPPI


def _coppie_d60() -> dict[str, str]:
    """vecchio -> nuovo percorso dello spostamento D60 (dalla migrazione 0488)."""
    sql = (Path(__file__).resolve().parents[2] / "core/migrations/0488_percorsi_comandi_ruoli.sql").read_text(encoding="utf-8")
    return dict(re.findall(r"\('([^']+)', '([^']+)'\)", sql.split("WITH m(vecchio, nuovo)", 2)[1]))


def percorsi_del_gruppo(nome_gruppo: str) -> set[str]:
    """Es. {"config history", "setup attiva", "ping"} per `/admin-bot`.

    Con il nome di un gruppo di prima di D60 (es. "admin") restituisce i percorsi che quel gruppo aveva
    e che oggi esistono sotto il nome nuovo."""
    if nome_gruppo not in GRUPPI:
        vecchi = {o[len(nome_gruppo) + 1:]: n for o, n in _coppie_d60().items() if o.startswith(nome_gruppo + " ")}
        esistenti = set()
        for rel, nuovo in vecchi.items():
            radice, _, resto = nuovo.partition(" ")
            if radice in GRUPPI and resto in percorsi_del_gruppo(radice):
                esistenti.add(rel)
        return esistenti
    trovati: set[str] = set()

    def scendi(gruppo: app_commands.Group, prefisso: str) -> None:
        for figlio in gruppo.commands:
            if isinstance(figlio, app_commands.Group):
                scendi(figlio, f"{prefisso}{figlio.name} ")
            else:
                trovati.add(f"{prefisso}{figlio.name}")

    scendi(GRUPPI[nome_gruppo], "")
    return trovati


def comando_nel_gruppo(nome_gruppo: str, percorso: str) -> app_commands.Command:
    """Il comando `/gruppo percorso`; AssertionError se non c'è. Accetta anche i percorsi di prima di D60."""
    nuovo = _coppie_d60().get(f"{nome_gruppo} {percorso}")
    if nome_gruppo not in GRUPPI and nuovo:
        nome_gruppo, _, percorso = nuovo.partition(" ")
    nodo = GRUPPI[nome_gruppo]
    for parte in percorso.split():
        nodo = nodo.get_command(parte)
        assert nodo is not None, f"/{nome_gruppo} {percorso}: manca '{parte}'"
    return nodo
