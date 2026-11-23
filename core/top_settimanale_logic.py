"""
core/top_settimanale_logic.py
=============================
La top 10 della settimana, pubblicata da sola il lunedì (LIV-061): quale settimana annunciare e come scrivere
l'elenco. Nessun accesso a Discord né al database.
Funzioni coperte: LIV-061
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.leveling_logic import week_key

MEDAGLIE = ("🥇", "🥈", "🥉")
POSIZIONI = 10


def settimana_precedente(adesso: datetime | None = None) -> str:
    """Chiave ISO della settimana appena finita (es. «2026-W46»), da annunciare."""
    momento = adesso or datetime.now(timezone.utc)
    return week_key(momento - timedelta(days=7))


def da_annunciare(ultima_annunciata: str | None, adesso: datetime | None = None) -> bool:
    """Vero se la settimana appena finita non è ancora stata annunciata (una sola volta, anche dopo un riavvio)."""
    return ultima_annunciata != settimana_precedente(adesso)


def riga(posizione: int, utente: int, quantita: int, unita: str) -> str:
    segno = MEDAGLIE[posizione - 1] if posizione <= len(MEDAGLIE) else f"{posizione}."
    return f"{segno} <@{utente}> — **{quantita}** {unita}"


def testo_top(voci: list[tuple[int, int]], unita: str) -> str:
    """Le prime 10 righe; «nessuna attività» se la settimana è vuota (un elenco vuoto sembrerebbe un errore)."""
    if not voci:
        return "_Nessuna attività registrata questa settimana._"
    return "\n".join(riga(i, u, q, unita) for i, (u, q) in enumerate(voci[:POSIZIONI], start=1))
