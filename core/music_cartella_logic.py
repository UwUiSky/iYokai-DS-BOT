"""
core/music_cartella_logic.py
============================
Cartella di brani dell'owner (MUS-018, D111): scansione sicura della cartella, titoli puliti per gli utenti
e percorso come lo vede il nodo Lavalink locale. Nessun Discord e nessuna rete qui dentro.
Funzioni coperte: SPEC §9 (catalogo MUS-018)
Dipende da: core/music_logic.py (percorso e identificatore locali)
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ESTENSIONI = frozenset({".mp3", ".flac", ".ogg", ".opus", ".wav", ".m4a", ".aac"})
MAX_FILE = 500  # brani in elenco (anche il menu di scelta ne mostra 25 alla volta)
MAX_BYTE_FILE = 300 * 1024 * 1024  # un brano pesante oltre 300 MiB non entra
MAX_BYTE_TOTALI = 20 * 1024**3  # 20 GiB in tutto
MAX_PROFONDITA = 3  # sotto-cartelle
MAX_TITOLO = 100
MAX_ANTEPRIME_IN_CODA = 50  # la playlist «Anteprime» mette in coda al massimo 50 brani
TITOLO_PREDEFINITO = "Brano senza titolo"
ANTEPRIME = "Anteprime"

_SPAZI = re.compile(r"\s+")
_ESTENSIONE_FINALE = re.compile(r"\.(mp3|flac|ogg|opus|wav|m4a|aac|mp4|webm|wma|aiff?)$", re.IGNORECASE)


@dataclass(frozen=True)
class BranoCartella:
    percorso: str  # relativo alla cartella, con «/»; mai mostrato agli utenti
    titolo: str  # titolo pulito
    dimensione: int
    modificato_ns: int


@dataclass(frozen=True)
class EsitoScansione:
    brani: list[BranoCartella]
    scartati: int  # file saltati (estensione, link fuori cartella, troppo grandi, oltre i tetti)
    troncata: bool  # vero se si e' arrivati a un tetto


def cartella_dell_owner(musica_cartella: str, radio_cartella: str) -> str:
    """MUSICA_CARTELLA_OWNER, altrimenti la cartella inediti della radio (MAIN_RADIO_LOCAL_FOLDER)."""
    return (musica_cartella or "").strip() or (radio_cartella or "").strip()


def _pulisci(testo: str) -> str:
    testo = unicodedata.normalize("NFKC", testo or "")
    testo = "".join(c for c in testo if c.isprintable() or c == " ")
    testo = testo.replace("`", "'").replace("*", "").replace("_", " ").replace("|", " ").replace("<", "").replace(">", "")
    testo = testo.replace("@", "").replace("[", "(").replace("]", ")")
    return _SPAZI.sub(" ", testo).strip()


def titolo_dal_nome(nome_file: str) -> str:
    """Un titolo pulito dal nome del file: niente estensione, niente cartelle, niente simboli del testo di Discord."""
    base = (nome_file or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = _ESTENSIONE_FINALE.sub("", base).replace("-", " - ").replace("_", " ")
    titolo = _pulisci(base)[:MAX_TITOLO].strip()
    return titolo or TITOLO_PREDEFINITO


def titolo_dai_metadati(testo, titolo_di_riserva: str) -> str:
    """
    Il titolo letto da Lavalink dai metadati del file. Si usa solo se sembra un titolo: un nome di file, un
    percorso o `local:` si scartano e resta il titolo pulito del file.
    """
    if not isinstance(testo, str):
        return titolo_di_riserva
    grezzo = testo.strip()
    basso = grezzo.lower()
    if (
        not grezzo
        or "/" in grezzo or "\\" in grezzo or basso.startswith(("local:", "file:", "unknown"))
        or _ESTENSIONE_FINALE.search(grezzo)
    ):
        return titolo_di_riserva
    pulito = _pulisci(grezzo)[:MAX_TITOLO].strip()
    return pulito or titolo_di_riserva


def percorso_per_il_nodo(radice_nodo: str, percorso_relativo: str) -> str:
    """Il percorso come lo vede il nodo Lavalink (con Docker e' il punto di montaggio)."""
    return f"{radice_nodo.rstrip('/')}/{percorso_relativo}"


def percorso_relativo_valido(percorso: str) -> bool:
    """Un percorso relativo senza «..», senza radice, senza caratteri di controllo."""
    if not percorso or len(percorso) > 500 or percorso.startswith(("/", "~")) or "\\" in percorso:
        return False
    if any(ord(c) < 32 for c in percorso):
        return False
    parti = percorso.split("/")
    return all(p not in ("", ".", "..") for p in parti)


def _dentro(radice_reale: Path, candidato: Path) -> bool:
    try:
        return candidato.resolve(strict=True).is_relative_to(radice_reale)
    except (OSError, RuntimeError):
        return False


def scansiona(radice: str | os.PathLike) -> EsitoScansione:
    """
    Elenca i file audio ammessi. Regole: solo le estensioni di ESTENSIONI; mai file nascosti; un link
    simbolico conta solo se il percorso vero resta DENTRO la cartella; tetti di file e di peso.
    Funzione sincrona (si lancia in un thread). Una cartella che manca da' un elenco vuoto.
    """
    try:
        radice_reale = Path(radice).resolve(strict=True)
    except (OSError, RuntimeError):
        return EsitoScansione([], 0, False)
    if not radice_reale.is_dir():
        return EsitoScansione([], 0, False)
    brani: list[BranoCartella] = []
    scartati = 0
    troncata = False
    peso_totale = 0
    for corrente, cartelle, files in os.walk(radice_reale, followlinks=False):
        profondita = len(Path(corrente).relative_to(radice_reale).parts)
        cartelle[:] = sorted(
            c for c in cartelle
            if not c.startswith(".") and profondita < MAX_PROFONDITA
            and _dentro(radice_reale, Path(corrente) / c)
        )
        for nome in sorted(files):
            if nome.startswith(".") or Path(nome).suffix.lower() not in ESTENSIONI:
                continue
            percorso = Path(corrente) / nome
            if not _dentro(radice_reale, percorso):  # link simbolico verso l'esterno
                scartati += 1
                continue
            try:
                vero = percorso.resolve(strict=True)
                stato = vero.stat()
            except OSError:
                scartati += 1
                continue
            if not vero.is_file() or stato.st_size <= 0 or stato.st_size > MAX_BYTE_FILE:
                scartati += 1
                continue
            if len(brani) >= MAX_FILE or peso_totale + stato.st_size > MAX_BYTE_TOTALI:
                scartati += 1
                troncata = True
                continue
            relativo = percorso.relative_to(radice_reale).as_posix()
            if not percorso_relativo_valido(relativo):
                scartati += 1
                continue
            peso_totale += stato.st_size
            brani.append(BranoCartella(relativo, titolo_dal_nome(nome), stato.st_size, stato.st_mtime_ns))
    return EsitoScansione(brani, scartati, troncata)

