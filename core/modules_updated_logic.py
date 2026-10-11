"""
core/modules_updated_logic.py
=================================
L'evento `modules_updated` (guild_id, modulo, attivo, utente) parte da OGNI
percorso che cambia lo stato dei moduli (M 10.13): salvataggio di
`/admin setup attiva`, wizard, importazione, reset e rollback. Chi cambia
molti moduli in un colpo (import, reset, rollback) confronta lo stato
prima e dopo: si emette solo per i moduli davvero cambiati.
"""

from __future__ import annotations

from typing import Any, Mapping


def moduli_cambiati(prima: Mapping[str, Any], dopo: Mapping[str, Any]) -> list[tuple[str, bool]]:
    """(modulo, nuovo stato) per i moduli il cui stato è diverso; un modulo assente vale spento."""
    cambiati: list[tuple[str, bool]] = []
    for nome in sorted(set(prima) | set(dopo)):
        prima_attivo = bool(prima.get(nome, False))
        dopo_attivo = bool(dopo.get(nome, False))
        if prima_attivo != dopo_attivo:
            cambiati.append((nome, dopo_attivo))
    return cambiati


async def stato_moduli(database, guild_id: int) -> dict[str, Any]:
    """Lo stato attuale dei moduli di un server (nome -> attivo)."""
    return dict((await database.get_full_config(guild_id))["modules"])


def emetti_modules_updated(
    client, guild_id: int, prima: Mapping[str, Any], dopo: Mapping[str, Any], user_id: int | None
) -> int:
    """Emette `modules_updated` per ogni modulo cambiato; restituisce quanti."""
    cambiati = moduli_cambiati(prima, dopo)
    for nome, attivo in cambiati:
        client.dispatch("modules_updated", guild_id, nome, attivo, user_id)
    return len(cambiati)
