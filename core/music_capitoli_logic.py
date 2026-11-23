"""
core/music_capitoli_logic.py
============================
Video lunghi (MUS-017, D111): analizzatore dell'elenco di brani con gli orari (descrizione del video o capitoli
dati da Lavalink o da YouTube) e calcolo di inizio e fine di ogni brano. Il video non si scarica e non si
taglia: ogni voce della coda fa ripartire lo stesso video al punto giusto e lo ferma all'orario del brano dopo.
Nessun Discord e nessuna rete qui dentro.
Funzioni coperte: SPEC §9 (catalogo MUS-017)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_VIDEO_MS = 8 * 3600 * 1000  # D111: un video oltre 8 ore e' rifiutato
MIN_VIDEO_CAPITOLI_MS = 10 * 60 * 1000  # sotto i 10 minuti l'elenco non si cerca nemmeno
MAX_VOCI = 100
MIN_VOCI = 3  # come i capitoli di YouTube: meno di 3 non e' un elenco
MAX_TESTO = 20_000  # della descrizione si legge solo l'inizio
MAX_RIGHE = 1_000
MAX_TITOLO = 100
MIN_DURATA_VOCE_MS = 5_000  # una voce piu' corta di 5 secondi non e' un brano
TITOLO_PREDEFINITO = "Brano"

# 1:02:03, 01:02:03, 0:00, 00:00, 75:30 (minuti oltre 59 senza ore). Mai piu' di 3 cifre per i minuti.
_ORA = r"(?:(\d{1,2}):)?(\d{1,3}):([0-5]\d)"
_PARENTESI_APERTE = r"[\[\(\{<]?"
_PARENTESI_CHIUSE = r"[\]\)\}>]?"
_NUMERO_ELENCO = r"(?:\d{1,3}\s*[.)\-:]\s+)?"  # «1. », «02) »
_PUNTO_ELENCO = r"[\s\-–—•*>·▶►]*"
_SEPARATORE = r"[\s\-–—:|.,;~/\\)\]>•·*]*"
_INIZIO = re.compile(rf"^{_PUNTO_ELENCO}{_NUMERO_ELENCO}{_PARENTESI_APERTE}\s*{_ORA}\s*{_PARENTESI_CHIUSE}{_SEPARATORE}(.*)$")
_FINE = re.compile(rf"^(.*?){_SEPARATORE}{_PARENTESI_APERTE}\s*{_ORA}\s*{_PARENTESI_CHIUSE}\s*$")
_URL = re.compile(r"https?://[^\s)\]>]+|www\.[^\s)\]>]+", re.IGNORECASE)
_SPAZI = re.compile(r"\s+")


@dataclass(frozen=True)
class Voce:
    titolo: str
    inizio_ms: int
    fine_ms: int  # l'orario del brano dopo (l'ultimo: la fine del video)


def orario_in_ms(ore: str | None, minuti: str, secondi: str) -> int | None:
    """Da «1:02:03» o «0:00» ai millisecondi. Con le ore i minuti stanno tra 0 e 59."""
    m, s = int(minuti), int(secondi)
    h = int(ore) if ore else 0
    if ore and m > 59:
        return None
    return ((h * 60 + m) * 60 + s) * 1000


def titolo_pulito(testo: str) -> str:
    """Il titolo di una voce: senza link, simboli del testo di Discord, caratteri di controllo e spazi doppi."""
    t = unicodedata.normalize("NFKC", testo or "")
    t = _URL.sub("", t)
    t = "".join(c for c in t if c.isprintable() or c == " ")
    for brutto in ("`", "*", "|", "<", ">", "@", "~", "\\"):
        t = t.replace(brutto, " ")
    t = t.replace("[", "(").replace("]", ")").replace("_", " ")
    t = t.replace("()", " ")  # resti di un link tolto dentro le parentesi
    t = _SPAZI.sub(" ", t).strip(" -–—:.,;/")
    while t.endswith(")") and t.count(")") > t.count("("):  # parentesi rimasta senza compagna
        t = t[:-1].rstrip()
    while t.startswith("(") and t.count("(") > t.count(")"):
        t = t[1:].lstrip()
    return t[:MAX_TITOLO].strip()


def _riga_con_orario(riga: str):
    """(inizio_ms, titolo) se la riga comincia con un orario, altrimenti None."""
    trovato = _INIZIO.match(riga)
    if not trovato:
        return None
    ms = orario_in_ms(trovato.group(1), trovato.group(2), trovato.group(3))
    return None if ms is None else (ms, trovato.group(4))


def _riga_con_orario_in_fondo(riga: str):
    trovato = _FINE.match(riga)
    if not trovato:
        return None
    ms = orario_in_ms(trovato.group(2), trovato.group(3), trovato.group(4))
    return None if ms is None else (ms, trovato.group(1))


def _righe(testo: str) -> list[str]:
    return (testo or "")[:MAX_TESTO].splitlines()[:MAX_RIGHE]


def _voci_grezze(righe: list[str]) -> list[tuple[int, str]]:
    iniziali = [r for r in (_riga_con_orario(x) for x in righe) if r]
    if len(iniziali) >= MIN_VOCI:
        return iniziali
    finali = [r for r in (_riga_con_orario_in_fondo(x) for x in righe) if r]
    return finali if len(finali) >= MIN_VOCI else iniziali


def costruisci_voci(grezze: list[tuple[int, str]], durata_ms: int | None = None) -> list[Voce]:
    """
    Da (inizio, titolo) alle voci con la fine. Regole: gli orari devono crescere (una riga fuori ordine o doppia
    si salta); si tiene solo cio' che sta dentro il video; una voce sotto i 5 secondi si salta; al massimo 100 voci;
    meno di 3 voci = nessun elenco (lista vuota).
    """
    limite = durata_ms if durata_ms and durata_ms > 0 else None
    buone: list[tuple[int, str]] = []
    for inizio, titolo in grezze:
        if limite is not None and inizio >= limite:
            continue
        if buone and inizio < buone[-1][0] + MIN_DURATA_VOCE_MS:
            continue
        buone.append((inizio, titolo))
        if len(buone) >= MAX_VOCI:
            break
    if len(buone) < MIN_VOCI:
        return []
    fine_video = limite if limite is not None else buone[-1][0] + 60_000  # senza durata l'ultima dura un minuto
    voci: list[Voce] = []
    for n, (inizio, titolo) in enumerate(buone):
        fine = buone[n + 1][0] if n + 1 < len(buone) else fine_video
        voci.append(Voce(titolo_pulito(titolo) or f"{TITOLO_PREDEFINITO} {n + 1}", inizio, fine))
    return voci


def analizza_elenco(testo: str, durata_ms: int | None = None) -> list[Voce]:
    """L'elenco di brani con orari trovato in un testo (la descrizione di un video); lista vuota se non c'e'."""
    return costruisci_voci(_voci_grezze(_righe(testo)), durata_ms)


def voci_da_capitoli(capitoli, durata_ms: int | None = None) -> list[Voce]:
    """
    I capitoli dati da Lavalink o da YouTube: lista di dizionari con un titolo (`title`/`name`) e un inizio in
    millisecondi (`start`/`startTime`/`start_time`). Voci storte si saltano.
    """
    if not isinstance(capitoli, (list, tuple)):
        return []
    grezze: list[tuple[int, str]] = []
    for c in capitoli[:MAX_VOCI * 2]:
        if not isinstance(c, dict):
            continue
        inizio = next((c[k] for k in ("start", "startTime", "start_time") if k in c), None)
        titolo = next((c[k] for k in ("title", "name") if isinstance(c.get(k), str)), "")
        if isinstance(inizio, bool) or not isinstance(inizio, (int, float)) or inizio < 0 or inizio > MAX_VIDEO_MS:
            continue
        grezze.append((int(inizio), titolo))
    grezze.sort(key=lambda g: g[0])
    return costruisci_voci(grezze, durata_ms)


def video_troppo_lungo(durata_ms, is_stream: bool = False) -> bool:
    """D111: oltre 8 ore il video e' rifiutato (una diretta ha durata ignota e non conta)."""
    return not is_stream and isinstance(durata_ms, int) and durata_ms > MAX_VIDEO_MS
