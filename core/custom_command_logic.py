"""
core/custom_command_logic.py
============================
Logica pura dei comandi personalizzati (tag, NF-09, SPEC §22.5): nomi,
prefisso, testo con segnaposto, pausa, azione sul ruolo.
Funzioni coperte: SPEC §22 (NF-09)
"""

from __future__ import annotations

import re
from datetime import datetime

import discord

from core.template_renderer import render_template

MAX_TAG = 50  # per server (gratis)
MAX_NOME = 32
MAX_TESTO = 2000
MAX_ARGOMENTI = 200
MAX_PAUSA = 3600
AZIONI_RUOLO = ("nessuna", "dai", "togli", "alterna")

_NOME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
# Il prefisso: da 1 a 3 simboli, mai lettere o cifre, mai caratteri che Discord legge come
# comando o menzione.
_PREFISSO_VIETATI = set("/@#<>*_`~|\\")


def normalizza_nome(grezzo: str) -> str | None:
    """Il nome in minuscolo se valido (lettere a-z, cifre, - e _; 1-32), altrimenti None."""
    nome = grezzo.strip().lower()
    return nome if _NOME_RE.match(nome) else None


def valida_prefisso(prefisso: str) -> str | None:
    """None se il prefisso va bene, altrimenti il motivo in italiano."""
    if not 1 <= len(prefisso) <= 3:
        return "Il prefisso deve avere da 1 a 3 caratteri."
    for c in prefisso:
        if c.isalnum() or c.isspace():
            return "Il prefisso non può contenere lettere, cifre o spazi."
        if c in _PREFISSO_VIETATI:
            return "Quel simbolo ha un significato per Discord: scegline un altro (per esempio ! ? . $)."
    return None


def nome_da_messaggio(contenuto: str, prefisso: str | None) -> tuple[str, str] | None:
    """Da `!regole uno due` a ("regole", "uno due"); None se non è un tag col prefisso."""
    if not prefisso or not contenuto.startswith(prefisso):
        return None
    resto = contenuto[len(prefisso):]
    if not resto or resto[0].isspace():
        return None
    nome, _, argomenti = resto.partition(" ")
    nome = nome.strip().lower()
    if not _NOME_RE.match(nome):
        return None
    return nome, argomenti.strip()


_DA_UTENTI = frozenset({"args", "username"})


def costruisci_risposta(testo: str, valori: dict[str, str]) -> str:
    """
    Il testo del tag con i segnaposto sostituiti (mai str.format). Gli argomenti e il nome
    li scrive chi usa il comando: le menzioni lì dentro diventano testo inerte.
    """
    sicuri = {k: discord.utils.escape_mentions(v) if k in _DA_UTENTI else v for k, v in valori.items()}
    return render_template(testo, sicuri)


def pausa_residua(ultimo_uso: datetime | None, ora: datetime, secondi: int) -> float:
    """Secondi ancora da aspettare (0 se si può usare)."""
    if ultimo_uso is None or secondi <= 0:
        return 0
    passato = (ora - ultimo_uso).total_seconds()
    return max(secondi - passato, 0)


def azione_ruolo(azione: str, ha_ruolo: bool) -> str | None:
    """Cosa fare col ruolo: "dai", "togli" o None (niente da fare)."""
    if azione == "dai":
        return None if ha_ruolo else "dai"
    if azione == "togli":
        return "togli" if ha_ruolo else None
    if azione == "alterna":
        return "togli" if ha_ruolo else "dai"
    return None
