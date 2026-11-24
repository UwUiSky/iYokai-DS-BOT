"""
core/comandi_diretti.py
=======================
I comandi diretti (D137): comandi di primo livello (`/play`, `/ban`, ...) che sono il comando
lungo (`/music play`, `/mod-ban ban`, ...) con un altro nome. Chiamano LA STESSA funzione, con gli
stessi controlli (permesso predefinito, livello del gruppo, lista nera, abbonamento). La politica
dei comandi spenti, le statistiche e i livelli delle funzioni guardano il PERCORSO VERO.
Una sola tabella: `DIRETTI` (nome -> percorso vero). Il nome è uguale in tutte le lingue.
Funzioni coperte: D137
Dipende da: core/command_access.py (il controllo di livello, caricato al primo uso)
"""

from __future__ import annotations

from typing import Any

from discord import app_commands


# nome del comando diretto -> percorso vero del comando lungo
DIRETTI: dict[str, str] = {
    "play": "music play",
    "skip": "music skip",
    "stop": "music stop",
    "pause": "music pause",
    "resume": "music resume",
    "queue": "music coda mostra",
    "ban": "mod-ban ban",
    "kick": "mod-ban kick",
    "mute": "mod-sanzioni mute",
    "shadowban": "mod-sanzioni shadowban dai",
}

# percorso vero -> nome del comando diretto
NOME_DIRETTO_DI: dict[str, str] = {percorso: nome for nome, percorso in DIRETTI.items()}


class ComandoDiretto(app_commands.Command):
    """Comando di primo livello che duplica un comando lungo; `percorso_vero` è quello del comando lungo."""

    percorso_vero: str
    lungo: app_commands.Command


def percorso_vero(comando: Any) -> str:
    """Il percorso del comando per politica, statistiche e livelli: per un comando diretto è quello lungo."""
    if isinstance(comando, ComandoDiretto):
        return comando.percorso_vero
    return getattr(comando, "qualified_name", None)


def e_diretto(comando: Any) -> bool:
    return isinstance(comando, ComandoDiretto)


def crea_comando_diretto(
    nome: str, lungo: app_commands.Command, callback: Any, radice: Any
) -> ComandoDiretto:
    """
    Il comando diretto `nome` per il comando lungo `lungo` (già nel suo gruppo): stessa funzione,
    stessa descrizione e stessi permessi del gruppo radice (`default_permissions`, `guild_only`,
    contesti, livello). `callback` è la funzione originale del cog, con i suoi controlli.
    """
    diretto = ComandoDiretto(name=nome, description=lungo.description, callback=callback)
    diretto.binding = lungo.binding
    diretto.percorso_vero = lungo.qualified_name
    diretto.lungo = lungo
    diretto.default_permissions = radice.default_permissions
    diretto.guild_only = radice.guild_only
    diretto.allowed_contexts = radice.allowed_contexts
    diretto.allowed_installs = radice.allowed_installs
    livello = getattr(radice, "livello", None)
    if livello is not None:

        async def predicato(interaction) -> bool:
            from core.command_access import controlla

            return await controlla(interaction, livello)

        predicato.livello = livello  # letto dalla ricerca dei comandi
        diretto.checks.append(predicato)
    return diretto
