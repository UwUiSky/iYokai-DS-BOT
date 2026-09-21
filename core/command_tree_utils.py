"""
core/command_tree_utils.py
=============================
walk_commands() cammina ricorsivamente l'albero comandi: un
app_commands.Group (es. /owner, /reminder, /sticky) contiene
sottocomandi che bot.tree.get_commands() da solo non espande.
Condivisa da scripts/generate_command_list.py e da /search
(cogs/utility/command_search.py) — un solo posto che sa come
espandere l'albero, non due copie della stessa logica che
rischierebbero di divergere.
"""

from __future__ import annotations

from discord import app_commands


def walk_commands(
    command_list: list, prefix: str = ""
) -> list[tuple[str, str]]:
    """Restituisce (nome_completo, descrizione) per ogni comando
    foglia, incluso dentro i Group annidati."""
    risultati = []
    for cmd in command_list:
        nome_completo = f"{prefix}{cmd.name}" if not prefix else f"{prefix} {cmd.name}"
        if isinstance(cmd, app_commands.Group):
            risultati.extend(walk_commands(cmd.commands, prefix=nome_completo))
        else:
            risultati.append((nome_completo, cmd.description or "(nessuna descrizione)"))
    return risultati
