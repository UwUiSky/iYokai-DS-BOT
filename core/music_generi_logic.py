"""
core/music_generi_logic.py
==========================
Playlist per genere (MUS-014): controlli di genere, titolo e link scelti dall'owner, tetti e raggruppamento
per il menu. Nessun Discord e nessuna rete qui dentro.
Funzioni coperte: SPEC §9 (catalogo MUS-014)
Dipende da: core/music_sources.py (classifica_link)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.music_sources import classifica_link

MAX_GENERI = 25  # un menu a tendina regge 25 voci
MAX_PLAYLIST_PER_GENERE = 25
MAX_TOTALE = 200
GENERE_MAX = 30
TITOLO_MAX = 80
LINK_MAX = 300
TIPI_AMMESSI = ("playlist", "album")

_PAROLE = re.compile(r"^[\w .,'&+!()-]+$")


@dataclass(frozen=True)
class VoceGenere:
    genere: str
    titolo: str
    link: str


def _pulito(testo: str) -> str:
    """Spazi singoli; a capo, tabulazioni e caratteri di controllo rendono il testo non valido (stringa vuota)."""
    if any(ord(c) < 32 for c in (testo or "")):
        return ""
    return " ".join((testo or "").split())


def genere_valido(testo: str) -> str | None:
    pulito = _pulito(testo)
    if not (2 <= len(pulito) <= GENERE_MAX) or not _PAROLE.match(pulito):
        return None
    return pulito


def titolo_valido(testo: str) -> str | None:
    pulito = _pulito(testo)
    if not (1 <= len(pulito) <= TITOLO_MAX) or not _PAROLE.match(pulito):
        return None
    return pulito


def link_valido(testo: str) -> str | None:
    """Un link https di una playlist o di un album di una fonte nota; None per tutto il resto."""
    pulito = (testo or "").strip()
    if not pulito or len(pulito) > LINK_MAX or not pulito.lower().startswith("https://"):
        return None
    noto = classifica_link(pulito)
    return pulito if noto is not None and noto.tipo in TIPI_AMMESSI else None


def raggruppa(voci: list[VoceGenere]) -> dict[str, list[VoceGenere]]:
    """Per genere (senza differenza tra maiuscole), nell'ordine alfabetico; al massimo MAX_GENERI generi."""
    gruppi: dict[str, list[VoceGenere]] = {}
    nomi: dict[str, str] = {}
    for v in sorted(voci, key=lambda v: (v.genere.lower(), v.titolo.lower())):
        chiave = v.genere.lower()
        nomi.setdefault(chiave, v.genere)
        gruppi.setdefault(nomi[chiave], []).append(v)
    return dict(list(gruppi.items())[:MAX_GENERI])
