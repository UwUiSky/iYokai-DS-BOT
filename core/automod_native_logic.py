"""
core/automod_native_logic.py
============================
Funzioni semplici per le regole AutoMod native: come una parola vietata
diventa una voce con gli asterischi (AMD-013) e quali voci della lista
delle eccezioni servono per lasciar passare certi inviti (AMD-026/027).
Niente oggetti discord.py qui dentro.
Funzioni coperte: SPEC §6.1, §6.2 (AMD-013, AMD-026, AMD-027)
"""

from __future__ import annotations

import re

from core.automod_sync import MAX_KEYWORD_LENGTH
from core.phishing_logic import codici_invito

# Come la parola vale nei messaggi (gli asterischi sono quelli dell'AutoMod nativo).
MODI_PAROLA = {
    "intera": "{p}",  # solo la parola così com'è
    "dentro": "*{p}*",  # anche dentro altre parole
    "inizio": "{p}*",  # parole che cominciano così
    "fine": "*{p}",  # parole che finiscono così
}

# Le eccezioni di una regola sono al massimo 100 per Discord; ne usiamo 25.
MAX_VOCI_ECCEZIONI = 25
# Ogni codice d'invito vale 3 voci: discord.gg, discord.com/invite, discordapp.com/invite.
PREFISSI_INVITO = ("discord.gg/", "discord.com/invite/", "discordapp.com/invite/")
MAX_CODICI_INVITO = MAX_VOCI_ECCEZIONI // len(PREFISSI_INVITO)

_CODICE_NUDO = re.compile(r"^[A-Za-z0-9-]{2,32}$")


def parola_con_modo(parola: str, modo: str = "intera") -> str:
    """
    La voce da salvare per la parola, con gli asterischi del modo scelto.
    Gli asterischi scritti a mano si tolgono se il modo non è «intera».
    Solleva ValueError se la voce supera i 60 caratteri di Discord.
    """
    parola = parola.strip()
    if modo != "intera":
        parola = parola.strip("*")
    if not parola.strip("*"):
        raise ValueError("La parola è vuota.")
    voce = MODI_PAROLA[modo].format(p=parola)
    if len(voce) > MAX_KEYWORD_LENGTH:
        raise ValueError(
            f"Con gli asterischi la parola è lunga {len(voce)} caratteri: "
            f"il massimo di Discord è {MAX_KEYWORD_LENGTH}."
        )
    return voce


def stessa_parola(voce: str, richiesta: str) -> bool:
    """
    True se `richiesta` indica la voce salvata. Una parola senza asterischi
    indica tutte le sue forme (parola, *parola*, parola*, *parola).
    """
    voce, richiesta = voce.lower(), richiesta.strip().lower()
    if voce == richiesta:
        return True
    return "*" not in richiesta and voce.strip("*") == richiesta


def codice_da_testo(testo: str) -> str | None:
    """Il codice d'invito da un link o da un codice scritto da solo."""
    testo = (testo or "").strip()
    trovati = codici_invito(testo)
    if trovati:
        return trovati[0]
    return testo if _CODICE_NUDO.match(testo) else None


def voci_per_codici(codici: tuple[str, ...]) -> tuple[str, ...]:
    """Le voci della lista delle eccezioni per questi codici (tre per codice)."""
    return tuple(f"{prefisso}{codice}" for codice in codici for prefisso in PREFISSI_INVITO)


def codici_da_voci(voci: tuple[str, ...]) -> tuple[str, ...]:
    """I codici d'invito dalle voci delle eccezioni (l'inverso di voci_per_codici)."""
    return tuple(v[len(PREFISSI_INVITO[0]) :] for v in voci if v.startswith(PREFISSI_INVITO[0]))


def codici_ammessi(
    permessi: tuple[str, ...], propri: tuple[str, ...]
) -> tuple[tuple[str, ...], bool]:
    """
    Codici da lasciar passare: prima quelli scelti dall'admin, poi gli inviti
    del server. Senza doppioni, al massimo MAX_CODICI_INVITO.
    Il secondo valore è True se alcuni codici sono rimasti fuori.
    """
    visti: dict[str, None] = {}
    for codice in (*permessi, *propri):
        visti.setdefault(codice, None)
    tutti = tuple(visti)
    return tutti[:MAX_CODICI_INVITO], len(tutti) > MAX_CODICI_INVITO
