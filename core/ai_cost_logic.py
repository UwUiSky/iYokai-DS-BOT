"""
core/ai_cost_logic.py
=====================
Conti dell'AI: stima dei token, costo di una chiamata, quote del server,
dell'utente e della funzione, tetto di spesa del mese, limite di richieste
al minuto per utente. Solo numeri, mai il testo.
Funzioni coperte: SPEC §25.4, §25.14, §25.15, §25.16, §25.23, §25.63 (AI-R-009..012, AI-R-014, AI-R-023, AI-R-069; catalogo AI-002, AI-008)
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass

RICHIESTE_AL_MINUTO_UTENTE = 6


def stima_token(testo: str) -> int:
    """Circa 4 caratteri per token: basta per contare prima della risposta."""
    return max(1, math.ceil(len(testo) / 4))


def costo_millesimi(costo_cent_milione: int, token: int) -> int:
    """Costo in millesimi di centesimo. `costo_cent_milione`: centesimi per milione di token."""
    if costo_cent_milione <= 0 or token <= 0:
        return 0
    return math.ceil(costo_cent_milione * token / 1000)


@dataclass(frozen=True)
class Quote:
    """Le quote scelte dall'admin (0 = nessun tetto, tranne il tetto di spesa: 0 = solo gratis)."""

    tetto_mensile_cent: int = 0
    utente_giorno: int = 20
    utente_30_giorni: int = 300
    funzione_giorno: int = 500
    immagini_settimana: int = 5


@dataclass(frozen=True)
class Uso:
    spesa_mese_millesimi: int = 0
    utente_oggi: int = 0
    utente_30_giorni: int = 0
    funzione_oggi: int = 0
    immagini_settimana: int = 0
    immagini_extra: int = 0


def quota_superata(quote: Quote, uso: Uso, *, immagine: bool = False, costo_previsto: int = 0) -> str | None:
    """
    Il motivo per cui la richiesta non può partire, o None. `costo_previsto` in millesimi:
    con tetto 0 passano solo le chiamate gratuite.
    """
    if costo_previsto > 0 and uso.spesa_mese_millesimi + costo_previsto > quote.tetto_mensile_cent * 1000:
        return "tetto"
    if quote.utente_giorno and uso.utente_oggi >= quote.utente_giorno:
        return "quota_utente"
    if quote.utente_30_giorni and uso.utente_30_giorni >= quote.utente_30_giorni:
        return "quota_utente_30"
    if quote.funzione_giorno and uso.funzione_oggi >= quote.funzione_giorno:
        return "quota_funzione"
    if immagine and quote.immagini_settimana and uso.immagini_settimana >= quote.immagini_settimana and uso.immagini_extra <= 0:
        return "quota_immagini"
    return None


def usa_credito_immagine(quote: Quote, uso: Uso) -> bool:
    """Oltre la quota della settimana l'immagine consuma una delle immagini comprate."""
    return bool(quote.immagini_settimana) and uso.immagini_settimana >= quote.immagini_settimana


def tetto_raggiunto(quote: Quote, uso: Uso) -> bool:
    """Spesa del mese arrivata al tetto: da qui solo fornitori gratuiti (D13)."""
    return uso.spesa_mese_millesimi >= quote.tetto_mensile_cent * 1000


class LimitatoreUtente:
    """Al massimo N richieste al minuto per persona (in memoria, per processo)."""

    def __init__(self, al_minuto: int = RICHIESTE_AL_MINUTO_UTENTE) -> None:
        self._al_minuto = al_minuto
        self._colpi: dict[int, deque[float]] = defaultdict(deque)

    def consenti(self, user_id: int, ora: float | None = None) -> bool:
        ora = time.monotonic() if ora is None else ora
        coda = self._colpi[user_id]
        while coda and coda[0] <= ora - 60:
            coda.popleft()
        if len(coda) >= self._al_minuto:
            return False
        coda.append(ora)
        if len(self._colpi) > 5000:
            for uid in [u for u, c in self._colpi.items() if not c][:1000]:
                del self._colpi[uid]
        return True


# ---------------------------------------------------------------- periodo di prova (AI-R-023)
GIORNI_PROVA = 7


def prova_attiva(inizio, ora=None, giorni: int = GIORNI_PROVA) -> bool:
    """Il periodo di prova dell'AI è iniziato e non è ancora finito (datetime con fuso)."""
    if inizio is None:
        return False
    from datetime import datetime, timedelta, timezone

    ora = ora or datetime.now(timezone.utc)
    return ora < inizio + timedelta(days=giorni)


def prova_finita(inizio, ora=None, giorni: int = GIORNI_PROVA) -> bool:
    return inizio is not None and not prova_attiva(inizio, ora, giorni)
