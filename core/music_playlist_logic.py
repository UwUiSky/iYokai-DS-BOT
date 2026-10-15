"""
core/music_playlist_logic.py
============================
Playlist salvate degli utenti: tetti, controllo del nome, brani da e
verso il formato salvato, file di esportazione e di importazione.
Funzioni coperte: SPEC §23 (NF-19), catalogo MUS-082
Dipende da: niente di Discord o Lavalink (logica pura).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MAX_PLAYLIST_PER_UTENTE = 25  # un elenco e un autocompletamento senza pagine
MAX_BRANI_PER_PLAYLIST = 200
NOME_MAX = 50
FILE_MAX_BYTE = 256 * 1024  # file di importazione (LIM: 10 MiB, qui molto meno)
FORMATO_FILE = "iyokai-playlist-1"
DURATA_MAX_MS = 24 * 3600 * 1000  # una durata letta da un file non supera un giorno

_NOME_VALIDO = re.compile(r"^[\w .,'!?()&+-]{1,50}$")


@dataclass(frozen=True)
class BranoSalvato:
    titolo: str
    uri: str | None
    durata_ms: int
    encoded: str

    def a_dizionario(self) -> dict:
        return {"title": self.titolo, "uri": self.uri, "length": self.durata_ms, "encoded": self.encoded}


def nome_valido(nome: str) -> str | None:
    """Il nome pulito, o None se vuoto, troppo lungo o con caratteri strani."""
    pulito = " ".join((nome or "").split())
    if not pulito or len(pulito) > NOME_MAX or not _NOME_VALIDO.match(pulito):
        return None
    return pulito


def brano_da_traccia(traccia) -> BranoSalvato | None:
    """Da una traccia wavelink (o simile) al formato salvato. None se manca `encoded`."""
    encoded = getattr(traccia, "encoded", None)
    if not encoded:
        return None
    return BranoSalvato(
        titolo=str(getattr(traccia, "title", "") or "Senza titolo")[:200],
        uri=getattr(traccia, "uri", None),
        durata_ms=int(getattr(traccia, "length", 0) or 0),
        encoded=str(encoded),
    )


def brani_da_coda(corrente, coda) -> tuple[list[BranoSalvato], int]:
    """
    Brano in corso più la coda, nel formato salvato, al massimo
    MAX_BRANI_PER_PLAYLIST. Restituisce anche quanti ne sono stati lasciati fuori.
    """
    tracce = ([corrente] if corrente is not None else []) + list(coda)
    brani = [b for b in (brano_da_traccia(t) for t in tracce) if b is not None]
    fuori = max(0, len(brani) - MAX_BRANI_PER_PLAYLIST)
    return brani[:MAX_BRANI_PER_PLAYLIST], fuori


def brani_da_json(valore) -> list[BranoSalvato]:
    """Dal JSON del database (o del file) ai brani. Le voci rotte si saltano."""
    dati = json.loads(valore) if isinstance(valore, (str, bytes)) else valore
    if not isinstance(dati, list):
        return []
    brani: list[BranoSalvato] = []
    for voce in dati:
        if not isinstance(voce, dict):
            continue
        encoded = voce.get("encoded")
        if not isinstance(encoded, str) or not encoded or len(encoded) > 4000:
            continue
        uri = voce.get("uri")
        try:
            durata = min(DURATA_MAX_MS, max(0, int(voce.get("length") or 0)))
        except (TypeError, ValueError, OverflowError):  # Infinity, NaN, testo
            durata = 0
        brani.append(
            BranoSalvato(
                titolo=str(voce.get("title") or "Senza titolo")[:200],
                uri=uri[:500] if isinstance(uri, str) else None,
                durata_ms=durata,
                encoded=encoded,
            )
        )
        if len(brani) >= MAX_BRANI_PER_PLAYLIST:
            break
    return brani


def brani_a_json(brani: list[BranoSalvato]) -> str:
    return json.dumps([b.a_dizionario() for b in brani[:MAX_BRANI_PER_PLAYLIST]])


def file_esportazione(nome: str, brani: list[BranoSalvato]) -> bytes:
    """MUS-082: il file da scaricare (JSON leggibile)."""
    dati = {"formato": FORMATO_FILE, "nome": nome, "brani": [b.a_dizionario() for b in brani]}
    return json.dumps(dati, ensure_ascii=False, indent=1).encode("utf-8")


def leggi_file_importazione(contenuto: bytes) -> tuple[list[BranoSalvato], str | None]:
    """
    MUS-082: brani da un file esportato. (brani, None) oppure ([], errore).
    Il file arriva da un utente: si controllano dimensione, formato e ogni voce.
    """
    if len(contenuto) > FILE_MAX_BYTE:
        return [], f"Il file supera {FILE_MAX_BYTE // 1024} KB."
    try:
        dati = json.loads(contenuto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):  # RecursionError: "[[[[…" annidato
        return [], "Il file non è un JSON valido."
    if not isinstance(dati, dict) or dati.get("formato") != FORMATO_FILE:
        return [], "Il file non è una playlist esportata da iYokai."
    brani = brani_da_json(dati.get("brani"))
    if not brani:
        return [], "Il file non contiene brani validi."
    return brani, None


_SORGENTI_VIETATE = {"local"}


def riferimenti_traccia(info) -> list[str] | None:
    """
    Una traccia decodificata da Lavalink (`info` di /v4/decodetracks) può
    essere suonata? Il brano salvato arriva anche da un file dell'utente: il
    suo `encoded` può nascondere un file locale del nodo o un URL interno
    (SSRF). None = rifiutata; se no, gli URL http(s) che il chiamante deve
    ancora controllare con `url_e_sicuro` (identificatore e uri).
    """
    if not isinstance(info, dict):
        return None
    if str(info.get("sourceName") or "").strip().lower() in _SORGENTI_VIETATE:
        return None
    da_controllare: list[str] = []
    for valore in (info.get("identifier"), info.get("uri")):
        if not isinstance(valore, str) or not valore:
            continue
        testo = valore.strip()
        basso = testo.lower()
        if basso.startswith(("http://", "https://")):
            da_controllare.append(testo)
        elif "://" in testo or basso.startswith(("/", "\\", "~", "file:", "local:")) or (
            len(testo) > 1 and testo[1] == ":" and testo[0].isalpha()
        ):
            return None  # altri schemi, percorsi di file
    return da_controllare


def dati_playlist_wavelink(nome: str, tracce: list) -> dict:
    """Il payload di una playlist Lavalink, dai brani decodificati (per wavelink.Playlist)."""
    return {"info": {"name": nome, "selectedTrack": -1}, "pluginInfo": {}, "tracks": list(tracce)}


def riga_elenco(nome: str, numero_brani: int, durata_ms: int) -> str:
    minuti = durata_ms // 60000
    return f"**{nome}** — {numero_brani} brani, {minuti} min"
