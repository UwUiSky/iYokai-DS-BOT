"""
core/ticket_ai_logic.py
=======================
Parte con l'AI di #139 (AI-R-104, AI-R-105): istruzioni e lettura delle risposte
per (1) il sollecito nella lingua dell'utente, (2) la scelta di una risposta
standard già approvata quando le parole non bastano, (3) il ruolo da chiamare
(moderatore o amministratore). L'AI non scrive mai testo libero all'utente:
traduce un nostro messaggio o sceglie tra le risposte approvate dallo staff.
Senza AI vale sempre la strada per parole (core/ticket_standard_logic.py).
Funzioni coperte: SPEC §25.97, §25.98
"""

from __future__ import annotations

from core.ai_testi_logic import LINGUE, estrai_json, nome_lingua, riconosci_lingua

MAX_SCELTE = 25
MAX_CARATTERI_RICHIESTA = 1500

SOLLECITO_LOCALE: dict[str, str] = {
    "it": "{utente} nessuno dello staff ha ancora risposto. Di cosa hai bisogno? Scrivilo qui: cerco una "
    "risposta già pronta, altrimenti avviso lo staff.",
    "en": "{utente} no staff member has replied yet. What do you need? Write it here: I will look for a "
    "ready answer, otherwise I will call the staff.",
}

ISTRUZIONI_TRADUCI = (
    "Traduci in {lingua} il messaggio di un bot di Discord. Lascia identici i segnaposto tra parentesi graffe. "
    "Rispondi solo con la traduzione."
)
ISTRUZIONI_SCEGLI = (
    "Sei lo smistamento dei ticket. Ecco le risposte approvate dallo staff (numero, titolo, parole chiave):\n"
    "{elenco}\nScegli quella che risponde alla richiesta dell'utente. Rispondi SOLO con JSON "
    '{{"numero": N}}; usa 0 se nessuna risponde davvero.'
)
ISTRUZIONI_RUOLO = (
    "Leggi la richiesta di un ticket. Serve un moderatore (comportamento di utenti, segnalazioni, sanzioni) "
    "o un amministratore (configurazione, ruoli, acquisti, collaborazioni, permessi)? Rispondi SOLO con JSON "
    '{"ruolo": "moderatore"} oppure {"ruolo": "amministratore"}; {"ruolo": "staff"} se non è chiaro.'
)


def lingua_utente(testi: list[str], predefinita: str = "it") -> str:
    """La lingua dai testi dell'utente; senza indizi quella del server, se nota, altrimenti l'italiano."""
    base = predefinita if predefinita in LINGUE else "it"
    return riconosci_lingua(" ".join(testi)[:MAX_CARATTERI_RICHIESTA], base) if testi else base


def sollecito_locale(lingua: str) -> str:
    """Il testo senza AI: italiano o inglese; per le altre lingue tutti e due."""
    if lingua in SOLLECITO_LOCALE:
        return SOLLECITO_LOCALE[lingua]
    return SOLLECITO_LOCALE["it"] + "\n" + SOLLECITO_LOCALE["en"].replace("{utente} ", "")


def istruzioni_traduzione(lingua: str) -> str:
    return ISTRUZIONI_TRADUCI.format(lingua=nome_lingua(lingua))


def traduzione_valida(originale: str, tradotto: str | None) -> str | None:
    """La traduzione si usa solo se tiene il segnaposto dell'utente e non è troppo lunga."""
    if not tradotto or "{utente}" not in tradotto or len(tradotto) > 3 * len(originale) + 200:
        return None
    return tradotto.strip()


def elenco_per_scelta(risposte: list[tuple[int, str, str]]) -> str:
    """(numero, titolo, parole chiave) → righe brevi; al massimo 25 risposte."""
    return "\n".join(f"{n}. {titolo[:100]} — {parole[:200]}" for n, titolo, parole in risposte[:MAX_SCELTE])


def leggi_scelta(testo: str | None, validi: set[int]) -> int | None:
    dati = estrai_json(testo or "")
    if not dati:
        return None
    try:
        numero = int(dati.get("numero"))
    except (TypeError, ValueError):
        return None
    return numero if numero in validi else None


def leggi_ruolo(testo: str | None) -> str | None:
    """"mod", "admin" o None (staff, risposta non chiara o AI ferma)."""
    dati = estrai_json(testo or "") or {}
    return {"moderatore": "mod", "amministratore": "admin"}.get(str(dati.get("ruolo", "")).strip().lower())
