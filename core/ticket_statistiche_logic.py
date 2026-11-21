"""
core/ticket_statistiche_logic.py
================================
Le righe di testo delle statistiche avanzate dei ticket (TKT-077): ogni valore sta in un campo di embed (1024).
Niente Discord, niente database.
Funzioni coperte: SPEC §13 (TKT-077)
"""

from __future__ import annotations

from core.ticket_log_logic import dettaglio_sicuro

MAX_CAMPO = 1024


def _entro(righe: list[str]) -> str:
    testo = "\n".join(righe)
    return testo if len(testo) <= MAX_CAMPO else testo[: MAX_CAMPO - 1] + "…"


def riga_giorni(giorni: list[tuple]) -> str:
    """«DD/MM: n» per giorno, gli ultimi 14 al massimo."""
    return _entro([f"{g:%d/%m}: {n}" for g, n in giorni[-14:]]) or "-"


def riga_ore(ore: list[tuple[int, int]]) -> str:
    """Le ore (UTC) in cui si aprono più ticket."""
    return _entro([f"{o:02d}:00-{o:02d}:59 UTC: {n}" for o, n in ore]) or "-"


def riga_motivi(motivi: list[tuple[str, int]]) -> str:
    """I motivi di chiusura più frequenti; il testo è di utenti: si pulisce e si accorcia."""
    righe = []
    for motivo, n in motivi:
        pulito = (dettaglio_sicuro(motivo) or "-").replace("\n", " ")[:60]
        righe.append(f"{pulito}: {n}")
    return _entro(righe) or "-"


def riga_operatori(operatori: list[tuple[int, float, int]]) -> str:
    """Voto medio per operatore (menzione dentro un embed: non avvisa nessuno)."""
    return _entro([f"<@{u}>: {media:.2f} ({voti})" for u, media, voti in operatori]) or "-"
