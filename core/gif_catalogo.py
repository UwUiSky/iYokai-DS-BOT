"""
core/gif_catalogo.py
====================
Catalogo delle GIF di reazione e di azione (data/gif_catalogo.json): quali voci esistono, il nome in
ogni lingua, i sinonimi e la categoria da chiedere a ciascuna fonte. Qui anche i suggerimenti del
completamento (solo dati locali: niente rete) e il controllo dei nomi scelti.
Funzioni coperte: SPEC §16 (FUN-081..135; D70, #131)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PERCORSO = Path(__file__).resolve().parent.parent / "data" / "gif_catalogo.json"
TIPI = ("reazione", "azione")
MAX_SUGGERIMENTI = 25  # tetto del completamento di Discord
MAX_NOME = 100  # nome e valore di un suggerimento
LINGUA_RIPIEGO = "en"


@dataclass(frozen=True)
class Voce:
    id: str
    fun: str
    tipo: str
    nomi: dict[str, str]
    sinonimi: tuple[str, ...]
    ricerca: str
    fonti: dict[str, str]

    def nome(self, lingua: str | None) -> str:
        base = (lingua or "it").split("-")[0].lower()
        return self.nomi.get(base) or self.nomi.get(LINGUA_RIPIEGO) or self.id

    @property
    def chiave_frase(self) -> str:
        """Chiave del testo nel catalogo catalogo dei testi."""
        return ("gif_reaz_" if self.tipo == "reazione" else "gif_az_") + self.id.replace("-", "_")


@lru_cache(maxsize=1)
def tutte() -> tuple[Voce, ...]:
    grezzo = json.loads(PERCORSO.read_text(encoding="utf-8"))["voci"]
    return tuple(
        Voce(v["id"], v["fun"], v["tipo"], dict(v["nomi"]), tuple(v["sinonimi"]), v["ricerca"], dict(v["fonti"]))
        for v in grezzo
    )


def voci(tipo: str) -> tuple[Voce, ...]:
    return tuple(v for v in tutte() if v.tipo == tipo)


def _norma(testo: str) -> str:
    return re.sub(r"\s+", " ", testo.strip().casefold())


def trova(tipo: str, scelto: str) -> Voce | None:
    """La voce di un valore scelto. Il completamento non è obbligatorio: accetta id, nome o sinonimo esatti."""
    chiave = _norma(scelto or "")
    if not chiave:
        return None
    for v in voci(tipo):
        if chiave == v.id or chiave in {_norma(n) for n in v.nomi.values()} or chiave in {_norma(s) for s in v.sinonimi}:
            return v
    return None


def suggerimenti(tipo: str, digitato: str, lingua: str | None = None) -> list[tuple[str, str]]:
    """Fino a 25 coppie (nome ≤100, valore ≤100). Prima chi inizia con il testo, poi chi lo contiene."""
    chiave = _norma(digitato or "")
    inizio: list[Voce] = []
    dentro: list[Voce] = []
    for v in voci(tipo):
        ricercabili = [_norma(v.nome(lingua)), v.id, *(_norma(n) for n in v.nomi.values()), *(_norma(s) for s in v.sinonimi)]
        if not chiave or any(r.startswith(chiave) for r in ricercabili):
            inizio.append(v)
        elif any(chiave in r for r in ricercabili):
            dentro.append(v)
    return [(v.nome(lingua)[:MAX_NOME], v.id[:MAX_NOME]) for v in (inizio + dentro)[:MAX_SUGGERIMENTI]]
