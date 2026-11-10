"""
core/voice_ticket_logic.py
==========================
Il saluto vocale di Yokai quando si apre un ticket: frase scelta con regole (senza AI), con il nome di chi apre
solo se si può pronunciare; senza nome la frase è fissa e resta in cache. Logica pura, senza Discord.
Funzioni coperte: SPEC §14.19 (passo 2, ticket)
"""

from __future__ import annotations

import random

from core.voice_text_logic import nome_pronunciabile

TONO_TICKET = "scherzosa"  # chi chiede aiuto deve prima di tutto capire la risposta

_CON_NOME = (
    "Ciao {nome}, sono Yokai. Scrivi pure qui cosa ti serve: lo staff ti risponde appena può.",
    "Ehi {nome}, sono Yokai. Racconta con calma cosa è successo: lo staff arriva presto.",
)
_SENZA_NOME = (
    "Ciao, sono Yokai. Scrivi pure qui cosa ti serve: lo staff ti risponde appena può.",
    "Ehi, sono Yokai. Racconta con calma cosa è successo: lo staff arriva presto.",
)


def frase_apertura(nome_grezzo: str | None, rng=random) -> tuple[str, bool]:
    """(frase, fissa). Fissa quando non c'è un nome da pronunciare."""
    nome = nome_pronunciabile(nome_grezzo)
    if nome:
        return rng.choice(_CON_NOME).format(nome=nome), False
    return rng.choice(_SENZA_NOME), True
