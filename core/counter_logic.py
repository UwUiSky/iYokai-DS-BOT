"""
core/counter_logic.py
=====================
Calcola il testo di ogni contatore (NF-16, SPEC §23.2): il numero da mostrare
per ogni tipo e il nome del canale. Funzioni pure.
Funzioni coperte: SPEC §23 (NF-16)
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_CONTATORI = 5  # per server
MAX_ETICHETTA = 80
MAX_NOME_CANALE = 100  # limite di Discord
INTERVALLO_SECONDI = 600  # LIM-3: 2 rinomine ogni 10 minuti per canale

TIPI = ("members", "online", "boosts", "goal")
ETICHETTE_DI_BASE = {
    "members": "👥 Membri: {n}",
    "online": "🟢 Online: {n}",
    "boosts": "🚀 Boost: {n}",
    "goal": "🎯 Obiettivo: {n}/{target}",
}
NOMI_TIPI = {
    "members": "membri",
    "online": "membri online",
    "boosts": "boost",
    "goal": "obiettivo di membri",
}


@dataclass(frozen=True)
class Istantanea:
    member_count: int
    online_count: int | None  # None = non si sa (serve una richiesta a parte)
    boost_count: int


def valore_del_contatore(kind: str, snap: Istantanea) -> int | None:
    """Il numero da mostrare; None se non è noto (il contatore resta com'è)."""
    if kind in ("members", "goal"):
        return snap.member_count
    if kind == "online":
        return snap.online_count
    if kind == "boosts":
        return snap.boost_count
    return None


def valida_etichetta(etichetta: str, kind: str) -> str | None:
    """None se l'etichetta va bene, altrimenti il motivo."""
    if not etichetta or "{n}" not in etichetta:
        return "L'etichetta deve contenere {n}, il posto del numero."
    if len(etichetta) > MAX_ETICHETTA:
        return f"L'etichetta supera {MAX_ETICHETTA} caratteri."
    if kind == "goal" and "{target}" not in etichetta:
        return "Per l'obiettivo l'etichetta deve contenere anche {target}."
    return None


def nome_canale(etichetta: str, valore: int, target: int | None) -> str:
    """Il nome del canale (al massimo 100 caratteri, come vuole Discord)."""
    testo = etichetta.replace("{n}", str(valore))
    if target is not None:
        testo = testo.replace("{target}", str(target))
    return testo[:MAX_NOME_CANALE]
