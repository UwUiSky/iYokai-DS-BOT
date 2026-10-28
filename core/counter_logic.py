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

TIPI = ("members", "online", "boosts", "goal", "tickets", "roles", "channels", "emojis")
ETICHETTE_DI_BASE = {
    "members": "👥 Membri: {n}",
    "online": "🟢 Online: {n}",
    "boosts": "🚀 Boost: {n}",
    "goal": "🎯 Obiettivo: {n}/{target}",
    "tickets": "🎫 Ticket aperti: {n}",
    "roles": "🏷️ Ruoli: {n}",
    "channels": "💬 Canali: {n}",
    "emojis": "😀 Emoji: {n}",
}
NOMI_TIPI = {
    "members": "membri",
    "online": "membri online",
    "boosts": "boost",
    "goal": "obiettivo di membri",
    "tickets": "ticket aperti",
    "roles": "ruoli",
    "channels": "canali",
    "emojis": "emoji",
}


@dataclass(frozen=True)
class Istantanea:
    member_count: int
    online_count: int | None  # None = non si sa (serve una richiesta a parte)
    boost_count: int
    ticket_aperti: int | None = None  # None = non letto (nessun contatore dei ticket nel server)
    ruoli: int = 0
    canali: int = 0
    emoji: int = 0


def valore_del_contatore(kind: str, snap: Istantanea) -> int | None:
    """Il numero da mostrare; None se non è noto (il contatore resta com'è)."""
    if kind in ("members", "goal"):
        return snap.member_count
    if kind == "online":
        return snap.online_count
    if kind == "boosts":
        return snap.boost_count
    if kind == "tickets":
        return snap.ticket_aperti
    if kind == "roles":
        return snap.ruoli
    if kind == "channels":
        return snap.canali
    if kind == "emojis":
        return snap.emoji
    return None


def valida_etichetta(etichetta: str, kind: str) -> str | None:
    """None se l'etichetta va bene, altrimenti il motivo."""
    if not etichetta or ("{n}" not in etichetta and "{breve}" not in etichetta):
        return "L'etichetta deve contenere {n} (o {breve}), il posto del numero."
    if len(etichetta) > MAX_ETICHETTA:
        return f"L'etichetta supera {MAX_ETICHETTA} caratteri."
    if kind == "goal" and "{target}" not in etichetta:
        return "Per l'obiettivo l'etichetta deve contenere anche {target}."
    return None


def abbrevia(numero: int) -> str:
    """STA-042: 1211 -> "1,21K", 2345678 -> "2,34M" (si tronca, non si arrotonda)."""
    for soglia, lettera in ((1_000_000, "M"), (1_000, "K")):
        if numero >= soglia:
            centesimi = numero * 100 // soglia
            intero, decimali = divmod(centesimi, 100)
            return f"{intero},{decimali:02d}".rstrip("0").rstrip(",") + lettera
    return str(numero)


def nome_canale(etichetta: str, valore: int, target: int | None) -> str:
    """Il nome del canale (al massimo 100 caratteri, come vuole Discord)."""
    testo = etichetta.replace("{n}", str(valore)).replace("{breve}", abbrevia(valore))
    if target is not None:
        testo = testo.replace("{target}", str(target))
    return testo[:MAX_NOME_CANALE]
