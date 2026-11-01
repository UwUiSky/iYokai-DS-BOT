"""
desktop/iyokai_desktop/appunti.py
=================================
Traduzione rapida e testi pronti dagli appunti: legge il testo copiato, lo fa tradurre dal servizio e lo rimette
negli appunti (la persona lo incolla da sé: il programma non scrive mai a nome suo). Tasto rapido: si collega al
comando `traduci-appunti` con le scorciatoie del sistema (vedi il README).
Funzioni coperte: SPEC D.8
"""

from __future__ import annotations

import shutil
import subprocess
import sys

MAX_APPUNTI = 3000


class ErroreAppunti(Exception):
    def __init__(self, codice: str) -> None:
        super().__init__(codice)
        self.codice = codice


def comandi(piattaforma: str | None = None, disponibile=shutil.which) -> tuple[list[str], list[str]]:
    """(comando che legge, comando che scrive) per il sistema. Nessuno strumento = ErroreAppunti."""
    piattaforma = piattaforma or sys.platform
    if piattaforma.startswith("win"):
        return ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], ["clip"]
    if piattaforma == "darwin":
        return ["pbpaste"], ["pbcopy"]
    if disponibile("wl-paste") and disponibile("wl-copy"):
        return ["wl-paste", "--no-newline"], ["wl-copy"]
    if disponibile("xclip"):
        return ["xclip", "-selection", "clipboard", "-o"], ["xclip", "-selection", "clipboard"]
    if disponibile("xsel"):
        return ["xsel", "--clipboard", "--output"], ["xsel", "--clipboard", "--input"]
    raise ErroreAppunti("strumento_mancante")


def leggi(esegui=subprocess.run, piattaforma: str | None = None) -> str:
    lettura, _ = comandi(piattaforma)
    try:
        risultato = esegui(lettura, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        raise ErroreAppunti("lettura_fallita") from None
    return risultato.stdout.decode("utf-8", errors="replace").strip()[:MAX_APPUNTI + 1]


def scrivi(testo: str, esegui=subprocess.run, piattaforma: str | None = None) -> None:
    _, scrittura = comandi(piattaforma)
    try:
        esegui(scrittura, input=testo.encode("utf-8"), capture_output=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        raise ErroreAppunti("scrittura_fallita") from None


def traduci_appunti(servizio, lingua: str, leggi_=None, scrivi_=None) -> str:
    """Traduce il testo negli appunti e lo rimette lì. Ritorna la traduzione."""
    leggi_, scrivi_ = leggi_ or leggi, scrivi_ or scrivi
    testo = leggi_()
    if not testo:
        raise ErroreAppunti("appunti_vuoti")
    if len(testo) > MAX_APPUNTI:
        raise ErroreAppunti("appunti_troppo_lunghi")
    tradotto = servizio.traduci(testo, lingua)
    if not tradotto:
        raise ErroreAppunti("traduzione_vuota")
    scrivi_(tradotto)
    return tradotto


def copia_risposta(servizio, nome: str, scrivi_=None) -> str:
    """Mette negli appunti una risposta salvata (per nome), da incollare. ErroreAppunti se non c'è."""
    for r in servizio.risposte():
        if r["nome"] == nome.strip().lower():
            (scrivi_ or scrivi)(r["testo"])
            return r["testo"]
    raise ErroreAppunti("risposta_non_trovata")
