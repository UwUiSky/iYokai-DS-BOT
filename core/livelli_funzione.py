"""
core/livelli_funzione.py
========================
Il livello di abbonamento di ogni funzione (gratuito, premium, VIP 5, VIP 20): un solo
punto che lo legge e lo scrive (D16), usato da `/premium`, `/vip` e dal futuro pannello.
Di default tutto è gratuito. Chi cambia un livello passa da `imposta_livello`: gli
ascoltatori registrati (il cog dei comandi) aggiornano l'albero senza riavvio.
Funzioni coperte: D57
Dipende da: core/command_groups.py (nomi dei comandi, solo per i test)
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

GRATUITO = "gratuito"
PREMIUM = "premium"
VIP5 = "vip5"
VIP20 = "vip20"
LIVELLI = (GRATUITO, PREMIUM, VIP5, VIP20)
ETICHETTE = {GRATUITO: "gratuito", PREMIUM: "Premium", VIP5: "VIP 5", VIP20: "VIP 20"}

# chiave: (nome leggibile, percorsi dei comandi della funzione)
FUNZIONI: dict[str, tuple[str, tuple[str, ...]]] = {
    "ai_immagini": ("Immagini AI", ("assistente immagina", "assistente ingrandisci", "assistente pacchetto")),
    "ai_testo": ("Testo AI", ("assistente riassumi", "assistente spiega", "assistente traduci", "assistente stile")),
    "ai_personaggi": ("Personaggi AI", ("assistente crea-personaggio", "assistente personaggio", "assistente mistero")),
    "ai_voce": ("Voce AI", ("assistente parla",)),
}

_livelli: dict[str, str] = {}
_ascoltatori: list[Callable[[], None]] = []


class LivelloNonValido(ValueError):
    """Funzione o livello sconosciuti."""


def livello_di(chiave: str, funzioni: dict | None = None) -> str:
    """Il livello della funzione (default: gratuito)."""
    return _livelli.get(chiave, GRATUITO)


def imposta_livello(chiave: str, livello: str, funzioni: dict | None = None) -> bool:
    """
    Scrive il livello di una funzione e avvisa gli ascoltatori se è cambiato.
    Restituisce True se è cambiato. LivelloNonValido se chiave o livello non esistono.
    """
    elenco = FUNZIONI if funzioni is None else funzioni
    if chiave not in elenco:
        raise LivelloNonValido(f"funzione sconosciuta: {chiave}")
    if livello not in LIVELLI:
        raise LivelloNonValido(f"livello sconosciuto: {livello}")
    if livello_di(chiave) == livello:
        return False
    if livello == GRATUITO:
        _livelli.pop(chiave, None)
    else:
        _livelli[chiave] = livello
    for ascoltatore in list(_ascoltatori):
        try:
            ascoltatore()
        except Exception:
            logger.exception("Ascoltatore dei livelli fallito")
    return True


def azzera_livelli() -> None:
    """Tutto gratuito (per i test)."""
    _livelli.clear()


def aggiungi_ascoltatore(funzione: Callable[[], None]) -> None:
    if funzione not in _ascoltatori:
        _ascoltatori.append(funzione)


def togli_ascoltatore(funzione: Callable[[], None]) -> None:
    if funzione in _ascoltatori:
        _ascoltatori.remove(funzione)


def funzioni_per_livello(livelli: tuple[str, ...], funzioni: dict | None = None) -> list[tuple[str, str, tuple[str, ...]]]:
    """[(livello, nome, percorsi)] delle funzioni che stanno in uno dei `livelli`, in ordine di livello."""
    elenco = FUNZIONI if funzioni is None else funzioni
    righe = []
    for livello in livelli:
        for chiave, (nome, percorsi) in elenco.items():
            if livello_di(chiave) == livello:
                righe.append((livello, nome, percorsi))
    return righe


def serve_premium(funzioni: dict | None = None) -> bool:
    """True se almeno una funzione è premium: allora esiste `/premium`."""
    return bool(funzioni_per_livello((PREMIUM,), funzioni))


def serve_vip(funzioni: dict | None = None) -> bool:
    """True se almeno una funzione è VIP 5 o VIP 20: allora esiste `/vip`."""
    return bool(funzioni_per_livello((VIP5, VIP20), funzioni))


def testo_elenco(livelli: tuple[str, ...], funzioni: dict | None = None) -> str:
    """Il messaggio di `/premium` e `/vip`: i comandi per livello, o una frase chiara se non ce ne sono."""
    righe = funzioni_per_livello(livelli, funzioni)
    if not righe:
        return "Al momento tutte le funzioni del bot sono gratuite per tutti."
    testo: list[str] = []
    for livello in livelli:
        scelte = [r for r in righe if r[0] == livello]
        if not scelte:
            continue
        testo.append(f"**{ETICHETTE[livello]}**")
        for _, nome, percorsi in scelte:
            testo.append(f"- {nome}: " + ", ".join(f"`/{p}`" for p in percorsi))
    return "\n".join(testo)
