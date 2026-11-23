"""
core/music_paese_logic.py
=========================
Paese delle ricerche (MUS-015, D111): codice ISO del paese, quale vale (server o globale dell'owner) e quali
brani scartare. Si scarta solo se la fonte dice chiaramente che il brano non e' ascoltabile in quel paese;
senza dato il brano passa. Nessun Discord e nessuna rete qui dentro.
Funzioni coperte: SPEC §9 (catalogo MUS-015)
"""

from __future__ import annotations

import re

_CODICE = re.compile(r"^[A-Za-z]{2}$")
# Dove i plugin di Lavalink o le API mettono i paesi in cui il brano si puo' ascoltare.
CAMPI_PAESI = ("availableMarkets", "available_markets", "availableCountries", "available_countries", "markets")

_paese_globale: str | None = None  # impostazione dell'owner; None = nessun limite (di base)


def paese_valido(testo) -> str | None:
    """Il codice ISO di 2 lettere in maiuscolo, o None se il testo non lo e'."""
    if not isinstance(testo, str):
        return None
    pulito = testo.strip()
    return pulito.upper() if _CODICE.match(pulito) and pulito.isascii() else None


def imposta_paese_globale(codice) -> None:
    """MUS-015: sostituisce il paese globale dell'owner (None o un valore non valido = nessun limite)."""
    global _paese_globale
    _paese_globale = paese_valido(codice)


def paese_globale() -> str | None:
    return _paese_globale


def paese_effettivo(paese_server) -> str | None:
    """Il paese che vale per un server: quello scelto dal server, altrimenti il globale dell'owner, altrimenti nessuno."""
    return paese_valido(paese_server) or _paese_globale


def paesi_dai_dati(dati) -> frozenset[str]:
    """I paesi dichiarati in un dizionario di dati di una fonte; insieme vuoto = la fonte non lo dice."""
    if not isinstance(dati, dict):
        return frozenset()
    for campo in CAMPI_PAESI:
        valore = dati.get(campo)
        if isinstance(valore, (list, tuple)) and valore:
            codici = {c for c in (paese_valido(v) for v in valore) if c}
            if codici:
                return frozenset(codici)
    return frozenset()


def paesi_della_traccia(traccia) -> frozenset[str]:
    dati = getattr(traccia, "raw_data", None)
    if not isinstance(dati, dict):
        return frozenset()
    return paesi_dai_dati(dati.get("pluginInfo")) or paesi_dai_dati(dati.get("info"))


def non_disponibile(traccia, paese: str | None) -> bool:
    """Vero solo se la fonte dichiara i paesi e quello scelto non c'e'. Senza dato: disponibile."""
    if not paese:
        return False
    paesi = paesi_della_traccia(traccia)
    return bool(paesi) and paese not in paesi


def togli_non_disponibili(tracce, paese: str | None) -> tuple[list, int]:
    """(tracce ammesse, quante scartate)."""
    ammesse = [t for t in tracce if not non_disponibile(t, paese)]
    return ammesse, len(tracce) - len(ammesse)
