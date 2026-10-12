"""
core/ban_appeal_logic.py
========================
Regole degli appelli contro i ban manuali (ban e tempban): un appello
ogni 24 ore, testo limitato, nomi dei bottoni, chi può decidere.
Funzioni coperte: SPEC §23 (NF-30, issue #101)
"""

from __future__ import annotations

from datetime import datetime, timedelta

from core.spam_trap_logic import APPEAL_COOLDOWN_SECONDS

# Un appello ogni 24 ore per utente e server (una sola regola, con lo spam-trap).
ATTESA_TRA_APPELLI = timedelta(seconds=APPEAL_COOLDOWN_SECONDS)
# Il testo dell'appello finisce nella descrizione di un embed (4096) e in un modulo (4000 al massimo).
MAX_TESTO_APPELLO = 1500
MIN_TESTO_APPELLO = 10

STATO_APERTO = "aperto"
STATO_ACCETTATO = "accettato"
STATO_RIFIUTATO = "rifiutato"

# Casi che un appello può contestare.
CASI_CON_APPELLO = ("ban", "tempban")


def attesa_rimasta(ultimo: datetime | None, adesso: datetime) -> timedelta | None:
    """None se può fare appello adesso, altrimenti quanto manca."""
    if ultimo is None:
        return None
    mancano = (ultimo + ATTESA_TRA_APPELLI) - adesso
    return mancano if mancano > timedelta(0) else None


def lunghezza_valida(testo: str) -> bool:
    return MIN_TESTO_APPELLO <= len(testo.strip()) <= MAX_TESTO_APPELLO


def attesa_a_parole(mancano: timedelta) -> str:
    ore = int(mancano.total_seconds() // 3600)
    minuti = int(mancano.total_seconds() % 3600 // 60)
    return f"{ore} ore e {minuti} minuti"
