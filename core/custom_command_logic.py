"""
core/custom_command_logic.py
============================
Logica pura dei comandi personalizzati (tag, NF-09, SPEC §22.5): nomi,
prefisso, testo con segnaposto, pausa, azione sul ruolo.
Funzioni coperte: SPEC §22 (NF-09)
"""

from __future__ import annotations

import random
import re
from datetime import datetime

import discord

from core.nome_logic import NOME_RE
from core.template_renderer import render_template

MAX_TAG = 50  # per server (gratis)
MAX_NOME = 32
MAX_TESTO = 4000  # un tag lungo esce in due messaggi (testo semplice) o in un embed (4096)
MAX_RISPOSTE_TAG = 5
MAX_PESO = 99
MAX_ARGOMENTI = 200
MAX_PAUSA = 3600
AZIONI_RUOLO = ("nessuna", "dai", "togli", "alterna")

# Il prefisso: da 1 a 3 simboli, mai lettere o cifre, mai caratteri che Discord legge come
# comando o menzione.
_PREFISSO_VIETATI = set("/@#<>*_`~|\\")


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
    if not NOME_RE.match(nome):
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


# ---------------------------------------------------------------- opzioni di comportamento (D69, B19-B20)
# Permessi Discord che si possono chiedere a chi usa un tag (≤ 25: stanno in una scelta).
PERMESSI_TAG: dict[str, str] = {
    "manage_messages": "gestire i messaggi", "manage_channels": "gestire i canali", "manage_roles": "gestire i ruoli",
    "manage_guild": "gestire il server", "manage_threads": "gestire i thread", "manage_nicknames": "gestire i nickname",
    "moderate_members": "mettere in timeout", "kick_members": "espellere", "ban_members": "bannare", "administrator": "essere amministratore",
}
INVII = ("canale", "privato", "altro")


def ha_il_permesso(permessi: discord.Permissions, richiesto: str | None) -> bool:
    """Senza permesso richiesto passano tutti; l'amministratore passa sempre."""
    if not richiesto:
        return True
    return richiesto in PERMESSI_TAG and (permessi.administrator or getattr(permessi, richiesto, False))


_RISPOSTA_CON_PESO = re.compile(r"^\s*(\d{1,4})\s*\|\s*(.*)$", re.DOTALL)


def leggi_risposta(campo: str) -> tuple[int, str] | None:
    """`3| ciao` → (3, "ciao"); senza peso vale 1. None se il campo è vuoto o il peso è fuori da 1–99."""
    campo = campo.strip()
    if not campo:
        return None
    trovato = _RISPOSTA_CON_PESO.match(campo)
    peso, testo = (int(trovato.group(1)), trovato.group(2).strip()) if trovato else (1, campo)
    if not testo or not 1 <= peso <= MAX_PESO:
        return None
    return peso, testo[:MAX_TESTO]


def scegli_pesata(risposte: list[tuple[int, str]], rng: random.Random | None = None) -> str | None:
    """Una risposta a caso, in proporzione al peso."""
    if not risposte:
        return None
    return (rng or random).choices([t for _, t in risposte], weights=[p for p, _ in risposte], k=1)[0]


def dividi_testo(testo: str, limite: int = 2000) -> list[str]:
    """Un testo oltre il limite esce in due messaggi, tagliato a un a-capo (o a uno spazio, o di netto)."""
    if len(testo) <= limite:
        return [testo]
    taglio = max(testo.rfind("\n", 0, limite), testo.rfind(" ", 0, limite))
    if taglio < limite // 2:
        taglio = limite
    primo, resto = testo[:taglio].rstrip(), testo[taglio:].lstrip("\n ")
    return [primo, resto[:limite]]
