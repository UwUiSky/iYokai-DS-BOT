"""
core/music_owner_logic.py
=========================
Comandi musicali dell'owner: descrizione dei nodi Lavalink (senza password), conteggio dei player
attivi, parola vietata in tutto il bot, coda del log di Lavalink ripulita dalle chiavi.
Funzioni coperte: SPEC §9 (catalogo MUS-067, MUS-068, MUS-069, MUS-070, MUS-063, MUS-011)
Dipende da: niente di Discord o Lavalink (logica pura).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

MAX_PAROLE_GLOBALI = 200
PAROLA_MIN, PAROLA_MAX = 2, 60
LOG_MAX_BYTE = 256 * 1024  # si manda solo la coda del file: sotto il tetto degli allegati (10 MiB)
PAUSA_RICONNETTI = 60.0  # secondi tra due «riconnetti» (nessuno spamma i server Lavalink)

_PAROLA_VALIDA = re.compile(r"^[\w .'&+!?-]{2,60}$")
# Valori che non devono mai uscire da un log: intestazioni e parametri con una chiave.
_SEGRETO_NEL_TESTO = re.compile(
    r"(?i)(authorization|password|passwd|secret|token|apikey|api_key|accesstoken|clientsecret)(\"?\s*[:=]\s*)(?:(?:bearer|basic|bot)\s+)?\S+"
)
_URL_CON_UTENTE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")


def parola_globale_valida(testo: str) -> str | None:
    """MUS-063: la parola pulita (senza spazi doppi) o None se vuota, corta, lunga o con caratteri strani."""
    pulita = " ".join((testo or "").split())
    if not (PAROLA_MIN <= len(pulita) <= PAROLA_MAX) or not _PAROLA_VALIDA.match(pulita):
        return None
    return pulita


def host_del_nodo(uri: str) -> str:
    """MUS-070: «host:porta» di un nodo. Mai la password né eventuali credenziali nell'indirizzo."""
    try:
        url = urlparse(uri or "")
        host = url.hostname or "?"
        porta = f":{url.port}" if url.port else ""
    except ValueError:
        return "?"
    return f"{host}{porta}"


def riga_nodo(chiave_bot: str, identificatore: str, uri: str, stato: str, players: int) -> str:
    """MUS-070: una riga per nodo."""
    return f"`{chiave_bot}` · {identificatore.split('@')[0]} · {host_del_nodo(uri)} · {stato} · {players} player"


def ripulisci_log(testo: str, segreti: list[str]) -> str:
    """
    MUS-069: toglie dal log ogni valore segreto noto (chiavi dell'ambiente, password) e ogni
    valore che segue «token:», «password=», «Authorization:»… e le credenziali dentro gli indirizzi.
    """
    for segreto in segreti:
        if segreto and len(segreto) >= 4:
            testo = testo.replace(segreto, "***")
    testo = _SEGRETO_NEL_TESTO.sub(lambda m: f"{m.group(1)}{m.group(2)}***", testo)
    return _URL_CON_UTENTE.sub(lambda m: f"{m.group(1)}***@", testo)


def coda_del_file(contenuto: bytes, massimo: int = LOG_MAX_BYTE) -> str:
    """MUS-069: gli ultimi `massimo` byte del log, cominciando da una riga intera."""
    if len(contenuto) > massimo:
        contenuto = contenuto[-massimo:]
        a_capo = contenuto.find(b"\n")
        if a_capo != -1:
            contenuto = contenuto[a_capo + 1:]
    return contenuto.decode("utf-8", errors="replace")
