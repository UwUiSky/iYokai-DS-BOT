"""
core/lore_nomi_logic.py
=======================
Nomi a tema per la moneta, i punti esperienza e i titoli dei livelli, e la lista dei temi per il primo avvio.
Funzioni coperte: SPEC §25.69, §25.47 (AI-R-076, AI-R-052)
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_NOME = 20
LIVELLI_PER_FASCIA = 10


@dataclass(frozen=True)
class NomiTema:
    moneta: str
    punti: str
    prefisso: str
    titoli: tuple[str, ...]  # uno ogni 10 livelli; l'ultimo vale per tutti i livelli più alti


NOMI: dict[str, NomiTema] = {
    "yokai": NomiTema("Mon", "Ki", "Rango", ("Viandante", "Apprendista", "Custode del santuario", "Maestro di spiriti", "Leggenda")),
    "fantasy": NomiTema("Corone", "Esperienza arcana", "Grado", ("Novizio", "Avventuriero", "Cavaliere", "Arcimago", "Eroe del regno")),
    "cyberpunk": NomiTema("Crediti", "Bit", "Livello neon", ("Script kiddie", "Netrunner", "Mercenario", "Fixer", "Fantasma della rete")),
    "horror": NomiTema("Ricordi", "Paura", "Soglia", ("Curioso", "Testimone", "Sopravvissuto", "Cacciatore di ombre", "Custode del buio")),
    "spazio": NomiTema("Crediti stellari", "Energia", "Classe", ("Cadetto", "Pilota", "Capitano", "Comandante di flotta", "Ammiraglio")),
    "pirati": NomiTema("Dobloni", "Gloria", "Grado", ("Mozzo", "Marinaio", "Nostromo", "Capitano", "Re dei pirati")),
}


def nomi_del_tema(tema: str | None) -> NomiTema | None:
    return NOMI.get(tema or "")


def nome_pulito(testo: str | None) -> str | None:
    """Il nome senza menzioni, a capo né formattazione, entro 20 caratteri; None se resta vuoto."""
    if not testo:
        return None
    pulito = " ".join(testo.split())
    pulito = "".join(c for c in pulito if c not in "@#`*_~|<>[]")[:MAX_NOME].strip()
    return pulito or None


def titolo_livello(tema: str | None, prefisso: str | None, livello: int) -> str:
    """«Rango 12: Apprendista». Senza tema né prefisso resta il solito «Livello 12»."""
    nomi = nomi_del_tema(tema)
    base = f"{nome_pulito(prefisso) or 'Livello'} {livello}"
    if nomi is None:
        return base
    fascia = min(max(livello, 0) // LIVELLI_PER_FASCIA, len(nomi.titoli) - 1)
    return f"{base}: {nomi.titoli[fascia]}"
