"""
core/odio_libreria_logic.py
===========================
Regole della libreria mondiale delle parole d'odio (D35), in logica pura:
quando una variante è valida, quando una candidata diventa globale.
Una variante nuova trovata dall'AI è «candidata» e vale solo nei server che
l'hanno segnalata; diventa globale con segnalazioni da server di almeno 3
proprietari diversi (server con almeno 25 membri) o con l'approvazione del
proprietario del bot. Parole troppo corte o comuni non diventano mai candidate.
Funzioni coperte: SPEC §6 (D35)
"""

from __future__ import annotations

from core.automod_parole_logic import MIN_LETTERE_VOCE, carica_base, pezzi

STATO_BASE = "base"
STATO_CANDIDATA = "candidata"
STATO_CONDIVISA = "condivisa"  # segnalata da abbastanza proprietari: vale ovunque, ma la giudica l'AI
STATO_APPROVATA = "approvata"  # approvata dall'owner: certa, si cancella senza chiedere all'AI
STATO_RIFIUTATA = "rifiutata"
STATI = (STATO_BASE, STATO_CANDIDATA, STATO_CONDIVISA, STATO_APPROVATA, STATO_RIFIUTATA)
STATI_GLOBALI = (STATO_BASE, STATO_APPROVATA)  # le parole certe: solo base e approvate dall'owner

SOGLIA_SERVER = 3  # proprietari diversi (uno per server) che devono segnalare la stessa variante
MIN_MEMBRI_PER_CONTARE = 25  # un server piu' piccolo segnala per se', ma non conta per la soglia
MIN_LETTERE_CANDIDATA = 4
MAX_PEZZI_VARIANTE = 2  # «due parole» al massimo
MAX_LUNGHEZZA_VARIANTE = 60  # come una parola dell'AutoMod di Discord
MAX_CANDIDATE_PER_SERVER = 200  # un solo server non può riempire la libreria
MAX_LINGUA = 8

# Parole comuni che l'AI (o un testo che la guida) non puo' far diventare candidate.
PAROLE_COMUNI = frozenset('''  # noqa: SIM905 (elenco lungo, piu' leggibile cosi')
ciao come cosa sono sei siamo hanno anche ancora questo questa quello quella tutto tutti
molto bene male grazie prego buongiorno buonasera notte giorno oggi domani ieri sempre
mai niente nulla dove quando perche fare fatto detto dire andare vado casa gente persona
persone amico amici ragazzo ragazza ragazzi uomo donna uomini donne bambino bambini
italiano italiani straniero stranieri nero neri nera nere bianco bianchi gioco giocare
server canale messaggio discord bot admin moderatore
hello thanks please yes what when where with this that there they them their have
from your people person friend friends game play player black white man woman
'''.split())


def pulisci_variante(testo: str) -> str | None:
    """La variante normalizzata (come la legge il filtro) o None se non va bene."""
    parti = pezzi(testo or "")
    if not 1 <= len(parti) <= MAX_PEZZI_VARIANTE:
        return None
    variante = " ".join(parti)
    if sum(len(p) for p in parti) < MIN_LETTERE_VOCE or len(variante) > MAX_LUNGHEZZA_VARIANTE:
        return None
    return variante


def variante_segnalabile(testo: str) -> str | None:
    """Come pulisci_variante, ma per le segnalazioni automatiche: niente parole corte, comuni o lecite."""
    variante = pulisci_variante(testo)
    if variante is None:
        return None
    parti = variante.split()
    if sum(len(p) for p in parti) < MIN_LETTERE_CANDIDATA or all(p.isdigit() for p in parti):
        return None
    if any(p in PAROLE_COMUNI for p in parti) or variante in carica_base()[1]:
        return None
    return variante


def pulisci_lingua(lingua: str) -> str:
    """Codice di lingua corto e in minuscolo (it, en, pt-br); altrimenti vuoto."""
    lingua = (lingua or "").strip().lower()
    if 2 <= len(lingua) <= MAX_LINGUA and all(c.isalpha() or c == "-" for c in lingua):
        return lingua
    return ""


def stato_dopo_segnalazione(stato: str, proprietari_diversi: int) -> str:
    """
    Una candidata con abbastanza proprietari diversi diventa condivisa (vale in tutti i server
    ma resta al giudizio dell'AI); solo l'owner la rende approvata, cioè certa (D39).
    Ogni altro stato resta com'è.
    """
    if stato == STATO_CANDIDATA and proprietari_diversi >= SOGLIA_SERVER:
        return STATO_CONDIVISA
    return stato
