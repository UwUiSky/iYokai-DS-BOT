"""
core/music_playlist_logic.py
============================
Playlist salvate degli utenti: tetti, controllo del nome, brani da e
verso il formato salvato, file di esportazione e di importazione.
Funzioni coperte: SPEC §23 (NF-19), catalogo MUS-082; MUS-071 salva la coda, MUS-078 carica,
MUS-079 elenco e dettaglio, MUS-080 elimina (comandi in cogs/music/playlist.py),
MUS-074 aggiungi, MUS-075 togli, MUS-076 senza doppioni, MUS-073 crea, MUS-077 rinomina
Dipende da: niente di Discord o Lavalink (logica pura).
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass

from core.music_sources import link_diretto_ammesso

MAX_PLAYLIST_PER_UTENTE = 25  # un elenco e un autocompletamento senza pagine
MAX_BRANI_PER_PLAYLIST = 200
NOME_MAX = 50
FILE_MAX_BYTE = 256 * 1024  # file di importazione (LIM: 10 MiB, qui molto meno)
FORMATO_FILE = "iyokai-playlist-1"
DURATA_MAX_MS = 24 * 3600 * 1000  # una durata letta da un file non supera un giorno

MAX_PLAYLIST_PER_SERVER = 25  # MUS-081
MAX_COLLABORATORI = 5  # MUS-086
NOME_PLAYLIST_DEL_GIORNO = "Oggi"  # MUS-045: la playlist automatica dei brani suonati oggi
NOME_PREFERITI = "Preferiti"  # MUS-085: la playlist dove finisce il cuore
LINK_ORIGINE_MAX = 300  # MUS-072/083
ALFABETO_CODICE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # senza 0/O e 1/I: si legge e si copia senza errori
CODICE_LUNGHEZZA = 8

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
    if str(getattr(traccia, "source", "") or "").lower() == "local":
        return None  # MUS-018: un file della cartella dell'owner non finisce mai in una playlist o in un file
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
    sorgente = str(info.get("sourceName") or "").strip().lower()
    if sorgente in _SORGENTI_VIETATE:
        return None
    # Un brano «http» è un link diretto che Lavalink scaricherebbe da dentro la rete del server: solo da host in elenco.
    if sorgente == "http" and not link_diretto_ammesso(str(info.get("uri") or "")):
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


def nuovo_codice() -> str:
    """MUS-084: un codice breve casuale per condividere una playlist (8 caratteri, ~40 bit)."""
    return "".join(secrets.choice(ALFABETO_CODICE) for _ in range(CODICE_LUNGHEZZA))


def codice_valido(testo: str) -> str | None:
    """MUS-084: il codice scritto da un utente, in maiuscole, oppure None se non ha la forma giusta."""
    codice = (testo or "").strip().upper().replace("-", "").replace(" ", "")
    if len(codice) != CODICE_LUNGHEZZA or any(c not in ALFABETO_CODICE for c in codice):
        return None
    return codice


def link_origine_valido(testo) -> str | None:
    """MUS-072/083: il link da ricordare come origine di una playlist: https, corto, senza spazi."""
    if not isinstance(testo, str):
        return None
    link = testo.strip()
    if not link.lower().startswith("https://") or len(link) > LINK_ORIGINE_MAX:
        return None
    return None if any(c.isspace() or ord(c) < 32 for c in link) else link


def nome_per_copia(nome: str, esistenti: set[str]) -> str:
    """MUS-084: il nome della copia ricevuta: quello originale, o «nome (2)», «nome (3)»… se è già preso."""
    if nome not in esistenti:
        return nome
    for n in range(2, 100):
        suffisso = f" ({n})"
        candidato = nome[: NOME_MAX - len(suffisso)].rstrip() + suffisso
        if candidato not in esistenti:
            return candidato
    return nome[: NOME_MAX - 5] + " (99)"


def chiave_brano(brano: BranoSalvato) -> str:
    """Cosa rende «lo stesso brano»: l'indirizzo se c'è, altrimenti il codice di Lavalink."""
    return (brano.uri or brano.encoded).strip().lower()


def togli_doppioni(brani: list[BranoSalvato]) -> tuple[list[BranoSalvato], int]:
    """MUS-076: i brani senza doppioni (resta la prima comparsa) e quanti ne sono stati tolti."""
    visti: set[str] = set()
    unici: list[BranoSalvato] = []
    for brano in brani:
        chiave = chiave_brano(brano)
        if chiave in visti:
            continue
        visti.add(chiave)
        unici.append(brano)
    return unici, len(brani) - len(unici)


def aggiungi_senza_doppioni(
    esistenti: list[BranoSalvato], nuovi: list[BranoSalvato]
) -> tuple[list[BranoSalvato], int, int, int]:
    """
    MUS-074: aggiunge in fondo i brani nuovi. Restituisce (elenco, aggiunti, doppioni, fuori):
    i doppioni non entrano, quelli oltre MAX_BRANI_PER_PLAYLIST restano fuori.
    """
    elenco = list(esistenti)
    presenti = {chiave_brano(b) for b in elenco}
    aggiunti = doppioni = fuori = 0
    for brano in nuovi:
        chiave = chiave_brano(brano)
        if chiave in presenti:
            doppioni += 1
        elif len(elenco) >= MAX_BRANI_PER_PLAYLIST:
            fuori += 1
        else:
            presenti.add(chiave)
            elenco.append(brano)
            aggiunti += 1
    return elenco, aggiunti, doppioni, fuori


def unisci_brani(esistenti: list[BranoSalvato], nuovi: list[BranoSalvato]):
    """Per `aggiorna_brani`: aggiunge senza doppioni; il risultato sono i conteggi (aggiunti, doppioni, fuori)."""
    elenco, aggiunti, doppioni, fuori = aggiungi_senza_doppioni(esistenti, nuovi)
    return elenco, (aggiunti, doppioni, fuori)


def togli_posizione(
    brani: list[BranoSalvato], posizione: int
) -> tuple[list[BranoSalvato], BranoSalvato | None]:
    """MUS-075: toglie il brano alla posizione (da 1). (elenco, tolto) oppure (elenco, None) se non c'è."""
    if posizione < 1 or posizione > len(brani):
        return list(brani), None
    elenco = list(brani)
    return elenco, elenco.pop(posizione - 1)


BRANI_PER_PAGINA = 15


def pagina_brani(brani: list[BranoSalvato], pagina: int) -> tuple[list[str], int]:
    """MUS-079: le righe di una pagina del dettaglio (da 1) e il numero di pagine."""
    pagine = max(1, -(-len(brani) // BRANI_PER_PAGINA))
    pagina = min(max(1, pagina), pagine)
    inizio = (pagina - 1) * BRANI_PER_PAGINA
    righe = [
        f"`{inizio + i + 1}.` {b.titolo[:80]} ({max(0, b.durata_ms) // 60000}:{max(0, b.durata_ms) // 1000 % 60:02d})"
        for i, b in enumerate(brani[inizio:inizio + BRANI_PER_PAGINA])
    ]
    return righe, pagine


def riga_elenco(nome: str, numero_brani: int, durata_ms: int) -> str:
    minuti = durata_ms // 60000
    return f"**{nome}** — {numero_brani} brani, {minuti} min"
