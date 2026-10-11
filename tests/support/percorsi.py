"""
tests/support/percorsi.py
=========================
Aiuto per i test dei gruppi F7: l'elenco dei percorsi ("sottogruppo comando")
dei comandi registrati in un gruppo condiviso di core/command_groups.py.
"""

from __future__ import annotations

from discord import app_commands

from core.command_groups import GRUPPI


def percorsi_del_gruppo(nome_gruppo: str) -> set[str]:
    """Es. {"config history", "setup attiva", "ping"} per `/admin`."""
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
    """Il comando `/gruppo percorso`; AssertionError se non c'è."""
    nodo = GRUPPI[nome_gruppo]
    for parte in percorso.split():
        nodo = nodo.get_command(parte)
        assert nodo is not None, f"/{nome_gruppo} {percorso}: manca '{parte}'"
    return nodo
