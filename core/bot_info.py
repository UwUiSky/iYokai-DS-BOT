"""
core/bot_info.py
================
Informazioni sul bot per `/utility info` (CFG-046, #122): versione del codice e link di invito.
Funzioni coperte: SPEC §20 (NF-05), catalogo #122
"""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path

import discord

RADICE = Path(__file__).resolve().parent.parent
# Permessi chiesti nell'invito: il bot ha moduli di sicurezza e moderazione, che ne richiedono molti.
PERMESSI_INVITO = discord.Permissions(administrator=True)


@functools.cache
def versione_codice() -> str:
    """Il commit in uso (7 caratteri) o «sconosciuta» se la cartella non è un repository git."""
    try:
        uscita = subprocess.run(
            ["git", "-C", str(RADICE), "rev-parse", "--short=7", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "sconosciuta"
    testo = uscita.stdout.strip()
    return testo if uscita.returncode == 0 and testo else "sconosciuta"


def url_invito(application_id: int | None, guild_id: int | None = None) -> str | None:
    """
    Il link per aggiungere il bot a un server, o None se l'ID dell'applicazione non c'è ancora.
    Con `guild_id` il server è già scelto nella pagina di invito.
    """
    if not application_id:
        return None
    extra = {"guild": discord.Object(id=guild_id)} if guild_id else {}
    return discord.utils.oauth_url(
        application_id, permissions=PERMESSI_INVITO, scopes=("bot", "applications.commands"), **extra
    )
