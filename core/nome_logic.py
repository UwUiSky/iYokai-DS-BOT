"""
core/nome_logic.py
==================
Il nome corto con cui si ritrova un elemento del server (tag, embed, modulo): minuscole a-z,
cifre, - e _, da 1 a 32 caratteri. Un solo punto, usato da tutti.
Funzioni coperte: SPEC §22 (NF-09, NF-17), §23 (NF-34)
"""

from __future__ import annotations

import re

NOME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


def normalizza_nome(grezzo: str) -> str | None:
    """Il nome in minuscolo se valido (lettere a-z, cifre, - e _; 1-32), altrimenti None."""
    nome = grezzo.strip().lower()
    return nome if NOME_RE.match(nome) else None
