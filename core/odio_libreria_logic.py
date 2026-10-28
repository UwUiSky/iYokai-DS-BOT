"""
core/odio_libreria_logic.py
===========================
Regole della libreria mondiale delle parole d'odio (D35), in logica pura:
quando una variante è valida, quando una candidata diventa globale.
Una variante nuova trovata dall'AI è «candidata» e vale solo nei server che
l'hanno segnalata; diventa globale con segnalazioni da almeno 3 server
diversi o con l'approvazione del proprietario del bot.
Funzioni coperte: SPEC §6 (D35)
"""

from __future__ import annotations

from core.automod_parole_logic import MIN_LETTERE_VOCE, pezzi

STATO_BASE = "base"
STATO_CANDIDATA = "candidata"
STATO_APPROVATA = "approvata"
STATO_RIFIUTATA = "rifiutata"
STATI = (STATO_BASE, STATO_CANDIDATA, STATO_APPROVATA, STATO_RIFIUTATA)
STATI_GLOBALI = (STATO_BASE, STATO_APPROVATA)

SOGLIA_SERVER = 3  # server diversi che devono segnalare la stessa variante
MAX_PEZZI_VARIANTE = 2  # «due parole» al massimo
MAX_LUNGHEZZA_VARIANTE = 60  # come una parola dell'AutoMod di Discord
MAX_CANDIDATE_PER_SERVER = 200  # un solo server non può riempire la libreria
MAX_LINGUA = 8


def pulisci_variante(testo: str) -> str | None:
    """La variante normalizzata (come la legge il filtro) o None se non va bene."""
    parti = pezzi(testo or "")
    if not 1 <= len(parti) <= MAX_PEZZI_VARIANTE:
        return None
    variante = " ".join(parti)
    if sum(len(p) for p in parti) < MIN_LETTERE_VOCE or len(variante) > MAX_LUNGHEZZA_VARIANTE:
        return None
    return variante


def pulisci_lingua(lingua: str) -> str:
    """Codice di lingua corto e in minuscolo (it, en, pt-br); altrimenti vuoto."""
    lingua = (lingua or "").strip().lower()
    if 2 <= len(lingua) <= MAX_LINGUA and all(c.isalpha() or c == "-" for c in lingua):
        return lingua
    return ""


def stato_dopo_segnalazione(stato: str, server_diversi: int) -> str:
    """Una candidata con abbastanza server diversi diventa approvata; ogni altro stato resta com'è."""
    if stato == STATO_CANDIDATA and server_diversi >= SOGLIA_SERVER:
        return STATO_APPROVATA
    return stato
