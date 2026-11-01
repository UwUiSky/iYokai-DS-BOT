"""
desktop/iyokai_desktop/rpc_avanzato.py
======================================
Funzioni che Discord permette solo alle applicazioni approvate (scope RPC): leggere le notifiche del client e
comandare microfono e cuffie. Qui sono SPENTE: finché Discord non approva l'applicazione, ogni tentativo risponde
«da attivare» e non apre nessun canale. Quando arriverà l'approvazione si scrive il corpo di `attiva()`.
Funzioni coperte: SPEC D.11
"""

from __future__ import annotations

FUNZIONI = {
    "notifiche_client": ("rpc.notifications.read", "Storico dei ping in tutti i server e nei DM"),
    "voce_muto": ("rpc.voice.write", "Muto e cuffie con un tasto"),
    "voce_canale": ("rpc.voice.write", "Cambio del canale vocale con un tasto"),
    "voce_lettura": ("rpc.voice.read", "Chi parla e in che canale sei"),
}


class DaAttivare(Exception):
    """La funzione esiste ma serve l'approvazione di Discord (`scope`)."""

    def __init__(self, funzione: str) -> None:
        super().__init__(funzione)
        self.funzione = funzione
        self.scope, self.descrizione = FUNZIONI[funzione]


def attiva(funzione: str, approvata: bool = False):
    """Spenta: senza approvazione di Discord solleva sempre DaAttivare. Funzione sconosciuta = KeyError."""
    if funzione not in FUNZIONI:
        raise KeyError(funzione)
    raise DaAttivare(funzione)


def elenco() -> list[tuple[str, str, str]]:
    """(nome, scope, descrizione) di ciò che aspetta l'approvazione."""
    return [(nome, scope, descrizione) for nome, (scope, descrizione) in FUNZIONI.items()]
