"""
core/music_logic.py
======================
Logica pura di Music (SPEC.md §9). Nessuna dipendenza da wavelink o
discord.py qui dentro — solo formattazione e parsing di stringhe.

Decisione presa con l'utente su come collegarsi a Lavalink: nodi
PUBBLICI gratuiti mantenuti dalla community, con più nodi configurati
in fallback, invece di self-hostare un processo Java sulla stessa VM
del bot (che peserebbe centinaia di MB extra su una macchina già
misurata con cura — vedi scripts/load_simulation.py). wavelink.Pool
gestisce da solo la scelta del nodo meno carico e il fallback tra
quelli configurati; qui serve solo interpretare la stringa di
configurazione (LAVALINK_NODES in core/config.py) in oggetti Python.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LavalinkNodeConfig:
    uri: str
    password: str


def parse_lavalink_nodes(raw: str) -> list[LavalinkNodeConfig]:
    """
    Formato: "uri1|password1,uri2|password2,...". Un pezzo vuoto o
    senza il separatore "|" (typo dell'utente nel file .env) viene
    ignorato silenziosamente, non fa fallire l'avvio del bot per un
    nodo scritto male mentre altri nodi validi sono configurati
    correttamente accanto.
    """
    if not raw.strip():
        return []

    nodi = []
    for pezzo in raw.split(","):
        pezzo = pezzo.strip()
        if not pezzo or "|" not in pezzo:
            continue
        uri, _, password = pezzo.partition("|")
        uri = uri.strip()
        password = password.strip()
        if not uri:
            continue
        nodi.append(LavalinkNodeConfig(uri=uri, password=password))
    return nodi


def format_duration(milliseconds: int) -> str:
    """
    Millisecondi -> "m:ss", o "h:mm:ss" se supera un'ora (formato
    classico di ogni player musicale, non un'invenzione di questo
    progetto).
    """
    secondi_totali = max(0, milliseconds) // 1000
    ore, resto = divmod(secondi_totali, 3600)
    minuti, secondi = divmod(resto, 60)
    if ore > 0:
        return f"{ore}:{minuti:02d}:{secondi:02d}"
    return f"{minuti}:{secondi:02d}"


def build_queue_display(
    current_title: str | None,
    queued_titles: list[str],
    max_shown: int = 10,
) -> str:
    """
    Testo pronto per un embed — non un oggetto discord.Embed qui
    dentro (questa funzione resta pura, senza discord.py), il
    chiamante lo mette dentro un embed come preferisce.
    """
    righe = []
    if current_title is not None:
        righe.append(f"▶️ **In riproduzione:** {current_title}")
    else:
        righe.append("Nessuna traccia in riproduzione.")

    if not queued_titles:
        righe.append("\nLa coda è vuota.")
        return "\n".join(righe)

    righe.append("\n**In coda:**")
    for indice, titolo in enumerate(queued_titles[:max_shown], start=1):
        righe.append(f"{indice}. {titolo}")

    rimanenti = len(queued_titles) - max_shown
    if rimanenti > 0:
        righe.append(f"...e altre {rimanenti} tracce.")

    return "\n".join(righe)
