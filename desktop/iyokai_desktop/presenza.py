"""
desktop/iyokai_desktop/presenza.py
==================================
Stato personalizzato (rich presence): controllo dei campi con i limiti di Discord, profili salvati sul PC e
rotazione automatica di più stati. Discord accetta poche modifiche ravvicinate: la rotazione non scende sotto
i 20 secondi.
Funzioni coperte: SPEC D.2, D.3, D.4
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

MIN_TESTO, MAX_TESTO = 2, 128
MAX_BOTTONI = 2
MAX_ETICHETTA = 32
MAX_URL = 512
MAX_CHIAVE_IMMAGINE = 300
MIN_INTERVALLO = 20  # secondi
MAX_PROFILI = 50
MAX_NOME_PROFILO = 40
_NOME = re.compile(r"^[\w .-]{1,40}$")


class ErrorePresenza(Exception):
    """`codice` è una parola fissa che il programma sa tradurre."""

    def __init__(self, codice: str, campo: str = "") -> None:
        super().__init__(codice if not campo else f"{codice}:{campo}")
        self.codice, self.campo = codice, campo


def _testo(valore, campo: str) -> str | None:
    if valore is None or valore == "":
        return None
    valore = str(valore).strip()
    if not MIN_TESTO <= len(valore) <= MAX_TESTO:
        raise ErrorePresenza("testo_lunghezza", campo)
    return valore


def _immagine(valore, campo: str) -> str | None:
    """Il nome di un'immagine caricata nell'applicazione, oppure un indirizzo https."""
    if not valore:
        return None
    valore = str(valore).strip()
    if len(valore) > MAX_CHIAVE_IMMAGINE or any(c.isspace() for c in valore):
        raise ErrorePresenza("immagine_non_valida", campo)
    if "://" in valore and not valore.startswith("https://"):
        raise ErrorePresenza("immagine_non_valida", campo)
    return valore


def _bottone(voce) -> dict:
    try:
        etichetta, url = (str(voce[0]).strip(), str(voce[1]).strip())
    except (TypeError, IndexError):
        raise ErrorePresenza("bottone_non_valido") from None
    if not 1 <= len(etichetta) <= MAX_ETICHETTA or not url.startswith("https://") or len(url) > MAX_URL or " " in url:
        raise ErrorePresenza("bottone_non_valido")
    return {"label": etichetta, "url": url}


def costruisci(attivita: dict, adesso: Callable[[], float] = time.time) -> dict:
    """
    Da ciò che scrive la persona (`details`, `state`, `large_image`, `large_text`, `small_image`, `small_text`,
    `bottoni`, `timer`) all'attività di Discord. Campi vuoti si saltano; troppo lunghi o storti = ErrorePresenza.
    `timer`: «avvio» (conta da adesso) o un numero di secondi alla fine (conto alla rovescia).
    """
    risultato: dict = {}
    for campo in ("details", "state"):
        testo = _testo(attivita.get(campo), campo)
        if testo:
            risultato[campo] = testo
    assets: dict = {}
    for chiave in ("large_image", "small_image"):
        img = _immagine(attivita.get(chiave), chiave)
        if img:
            assets[chiave] = img
    for chiave in ("large_text", "small_text"):
        testo = _testo(attivita.get(chiave), chiave)
        if testo:
            assets[chiave] = testo
    if assets:
        risultato["assets"] = assets
    bottoni = attivita.get("bottoni") or []
    if len(bottoni) > MAX_BOTTONI:
        raise ErrorePresenza("troppi_bottoni")
    if bottoni:
        risultato["buttons"] = [_bottone(b) for b in bottoni]
    timer = attivita.get("timer")
    if timer == "avvio":
        risultato["timestamps"] = {"start": int(adesso())}
    elif timer:
        try:
            secondi = int(timer)
        except (TypeError, ValueError):
            raise ErrorePresenza("timer_non_valido") from None
        if not 1 <= secondi <= 7 * 24 * 3600:
            raise ErrorePresenza("timer_non_valido")
        risultato["timestamps"] = {"end": int(adesso()) + secondi}
    if not risultato:
        raise ErrorePresenza("attivita_vuota")
    return risultato


class ArchivioProfili:
    """I profili salvati: un file JSON sul PC (nome -> campi). Scrittura sicura (file nuovo poi rinomina)."""

    def __init__(self, percorso: Path) -> None:
        self.percorso = Path(percorso)

    def _leggi(self) -> dict[str, dict]:
        try:
            dati = json.loads(self.percorso.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return dati if isinstance(dati, dict) else {}

    def _scrivi(self, dati: dict[str, dict]) -> None:
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        fd, temporaneo = tempfile.mkstemp(dir=self.percorso.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dati, f, ensure_ascii=False, indent=2)
        os.replace(temporaneo, self.percorso)

    def nomi(self) -> list[str]:
        return sorted(self._leggi())

    def carica(self, nome: str) -> dict | None:
        return self._leggi().get(nome)

    def salva(self, nome: str, attivita: dict) -> None:
        """Salva solo se la costruzione riesce: un profilo salvato si può sempre usare."""
        if not _NOME.match(nome or ""):
            raise ErrorePresenza("nome_profilo_non_valido")
        costruisci(attivita)
        dati = self._leggi()
        if nome not in dati and len(dati) >= MAX_PROFILI:
            raise ErrorePresenza("troppi_profili")
        dati[nome] = attivita
        self._scrivi(dati)

    def elimina(self, nome: str) -> bool:
        dati = self._leggi()
        if nome not in dati:
            return False
        del dati[nome]
        self._scrivi(dati)
        return True


def ruota(cliente, attivita: list[dict], intervallo: int, fermati: Event, giri: int | None = None) -> int:
    """
    Cambia stato ogni `intervallo` secondi, in cerchio, finché `fermati` non scatta (o dopo `giri` cambi: per i
    test). Ritorna quanti cambi ha fatto. Sotto il minimo = ErrorePresenza. Lo stato si toglie alla fine.
    """
    if intervallo < MIN_INTERVALLO:
        raise ErrorePresenza("intervallo_troppo_corto")
    pronte = [costruisci(a) for a in attivita]
    if len(pronte) < 2:
        raise ErrorePresenza("servono_due_stati")
    fatti = 0
    try:
        while not fermati.is_set() and (giri is None or fatti < giri):
            cliente.imposta_attivita(pronte[fatti % len(pronte)])
            fatti += 1
            if giri is not None and fatti >= giri:
                break
            fermati.wait(intervallo)
    finally:
        try:
            cliente.imposta_attivita(None)
        except Exception:  # noqa: BLE001 - Discord già chiuso: nulla da togliere
            pass
    return fatti
