"""
core/moderation_risposte.py
===========================
Come il bot risponde dopo una sanzione (messaggio normale, riga compatta, cancellato dopo N secondi) e
conferma a due tasti prima di sanzionare. Solo logica semplice, senza Discord.
Funzioni coperte: SPEC §5.13 (MOD-066, MOD-067)
"""

from __future__ import annotations

MODO_NORMALE = "normale"
MODO_COMPATTA = "compatta"
MODO_CANCELLA_DOPO = "cancella-dopo"
MODI = (MODO_NORMALE, MODO_COMPATTA, MODO_CANCELLA_DOPO)

SECONDI_MIN = 5
SECONDI_MAX = 300
SECONDI_BASE = 30
# Un messaggio di risposta a un comando si cancella solo finché il token dell'interazione vale (15 minuti).
VITA_TOKEN_S = 15 * 60
SECONDI_CONFERMA = 60
MAX_RIGA = 400
_CAMPI_COMPATTI = ("Utente", "Caso", "Durata", "Motivo")


def modo_valido(valore) -> str:
    return valore if valore in MODI else MODO_NORMALE


def secondi_validi(valore) -> int:
    """Secondi prima di cancellare la risposta: da 5 a 300, altrimenti il valore di base."""
    if isinstance(valore, bool) or not isinstance(valore, int):
        return SECONDI_BASE
    return valore if SECONDI_MIN <= valore <= SECONDI_MAX else SECONDI_BASE


def compatta(modo: str) -> bool:
    return modo in (MODO_COMPATTA, MODO_CANCELLA_DOPO)


def puo_cancellare(secondi: int, trascorsi: int = 0) -> bool:
    """True se la risposta si può ancora cancellare dopo `secondi` (il token dura 15 minuti)."""
    return trascorsi + secondi < VITA_TOKEN_S


def riga_compatta(titolo: str | None, campi: dict[str, str], *, nota: str | None = None) -> str:
    """Una riga sola: «Titolo · Utente · Caso #n · Motivo», al massimo MAX_RIGA caratteri."""
    pezzi = [titolo or ""]
    for nome in _CAMPI_COMPATTI:
        valore = campi.get(nome)
        if valore:
            pezzi.append(valore if nome != "Motivo" else f"«{valore[:150]}»")
    if nota:
        pezzi.append(nota)
    riga = " · ".join(p for p in pezzi if p)
    return riga if len(riga) <= MAX_RIGA else riga[: MAX_RIGA - 1] + "…"
