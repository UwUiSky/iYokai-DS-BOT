"""
core/automod_parole_logic.py
============================
Filtro delle parole vietate lato bot, in logica pura (niente Discord, niente I/O).
Normalizza il testo (maiuscole, accenti, cifre e simboli al posto delle lettere,
lettere simili di altri alfabeti, caratteri invisibili, markdown, separatori,
lettere ripetute, lettere censurate con * o █, testo girato con l'override
destra-sinistra) e lo confronta con le liste. Tiene anche gli ultimi messaggi
brevi di ogni utente, per la parola divisa in piu' messaggi. Tempo lineare,
nessuna regex con backtracking.
Funzioni coperte: SPEC §6 (AMD-014)
"""

from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

FILE_BASE = Path(__file__).resolve().parent.parent / "data" / "automod_parole_odio.txt"

MAX_TESTO = 8000  # caratteri guardati per messaggio
MAX_FINESTRA = 12  # pezzi corti uniti ("n i gg er")
MAX_UNITO = 32  # lunghezza massima del testo unito
MIN_LETTERE_VOCE = 3
MIN_DENTRO = 5  # le voci "dentro una parola" sono lunghe e senza ambiguita'

_SPOILER = re.compile(r"\|{2,}")  # un solo "|" vale i; "||" e' lo spoiler

# Cifre e simboli usati al posto delle lettere.
_LEET = {
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "6": "g", "7": "t", "8": "b", "9": "g",
    "@": "a", "$": "s", "!": "i", "|": "i", "+": "t", "€": "e", "£": "l", "¡": "i", "§": "s", "¢": "c",
    "⭕": "o", "○": "o", "◯": "o", "●": "o", "⚪": "o", "⚫": "o",  # cerchi al posto della o
}
# Markdown: si toglie e le lettere restano unite ("n*i*g").
_MARKDOWN = frozenset("*~`")
# Simboli che coprono una lettera ("n*gger"): nella lettura "con jolly" valgono una lettera qualsiasi.
_JOLLY = frozenset("*_#?█▓▒░■")
MAX_JOLLY = 2  # jolly per pezzo
MAX_PEZZI_JOLLY = 50  # pezzi con jolly provati per messaggio (solo quelli che potrebbero essere una voce)
MAX_ZONE_JOLLY = 8  # zone con jolly dentro pezzi lunghi, provate per messaggio
_RAGGIO_JOLLY = 14  # lettere guardate attorno a un jolly nei pezzi lunghi
# Caratteri che sembrano spazi vuoti ma sono lettere (riempitivi hangul): si tolgono.
_VUOTI = frozenset("\u115f\u1160\u3164\uffa0")
# Override destra-sinistra: il testo dopo si vede girato fino a "fine override" o a capo.
_RLO, _PDF = "\u202e", "\u202c"

_SIMILI = {}


def _aggiungi(sorgente: str, destinazione: str) -> None:
    for s, d in zip(sorgente, destinazione):
        _SIMILI[s] = d


_aggiungi("аьвсԁеғԍнікӏмпорԛгѕтуҳѡј", "abbcdefghiklmnopqrstuxwj")  # cirillico
_aggiungi("αβεηικμνορτυχγως", "abenikuvoptuxyws")  # greco
_aggiungi("ոօսց", "noug")  # armeno
_aggiungi("øðđħıłɡɑʀɴɪɢʜʟᴇᴀᴏᴜᴅᴋᴛᴍᴘʙᴄᴊᴡᴠʏᴢꜱꜰɱƞŋ", "oddhilgarnighleaoudktmpbcjwvyzsfmnn")  # latino esteso e maiuscoletto
_aggiungi("ꓐꓑꓓꓔꓖꓗꓙꓚꓜꓝꓟꓠꓡꓢꓣꓦꓧꓪꓫꓬꓮꓰꓲꓳꓴ", "bpdtgkjczfmnlsrvhwxyaeiou")  # lisu
_aggiungi("ᎠᎡᎢᎥᎩᎪᎫᎬᏃᏇᏋᏍᏀᏂᏃᏏᏒᏔᏕᏙᏚᏞᏟᏢᏦᏴ", "drtiyajewmhyghzbrwsvslcpkb")  # cherokee (le minuscole diventano queste)
_aggiungi("ƒʂȿɗɖƀɓƈȼɇɛǥɠɦʝɩɨƙɍɽɾƭʈŧɏƶȥ", "fssddbbcceegghjiikrrrtttyzz")  # latino con uncino o barra
_SIMILI["æ"] = "ae"
_SIMILI["œ"] = "oe"
_SIMILI["ß"] = "ss"


def _calcola(ch: str) -> str:
    """Cosa diventa un carattere: lettere, " " (separatore) oppure "" (si toglie)."""
    if ch in _LEET:
        return _LEET[ch]
    if ch in _MARKDOWN or ch in _VUOTI:
        return ""
    o = ord(ch)
    if 0x1F1E6 <= o <= 0x1F1FF:  # lettere-bandiera
        return chr(97 + o - 0x1F1E6)
    if 0x1F150 <= o <= 0x1F169:  # lettere cerchiate nere
        return chr(97 + o - 0x1F150)
    if 0x1F170 <= o <= 0x1F189:  # lettere quadrate nere
        return chr(97 + o - 0x1F170)
    if ch.isspace():
        return " "
    cat = unicodedata.category(ch)
    if cat[0] == "M" or cat in ("Cf", "Cc", "Cs", "Co", "Cn"):  # diacritici, invisibili, controllo
        return ""
    if ch.isalpha():
        piccola = ch.casefold()
        return "".join(_SIMILI.get(c, c) for c in piccola)
    return " "


_CACHE: dict[str, str] = {}


def _carattere(ch: str) -> str:
    r = _CACHE.get(ch)
    if r is None:
        r = _calcola(ch)
        if len(_CACHE) < 8000:
            _CACHE[ch] = r
    return r


def _prepara(testo: str) -> str:
    return _SPOILER.sub("", unicodedata.normalize("NFKD", testo[:MAX_TESTO]))


def pezzi(testo: str) -> list[str]:
    """Il testo normalizzato, diviso in pezzi di sole lettere."""
    unito = "".join(_carattere(c) for c in _prepara(testo))
    return unito.split()


def _pezzi_con_jolly(testo: str) -> list[str]:
    """Pezzi in cui i simboli che coprono una lettera restano come "?" (solo tra due lettere)."""
    unito = "".join("?" if c in _JOLLY else _carattere(c) for c in _prepara(testo))
    return [p for p in (x.strip("?") for x in unito.split()) if "?" in p]


def come_si_vede(testo: str) -> str:
    """Il testo come appare: dopo l'override destra-sinistra le lettere si leggono girate."""
    if _RLO not in testo:
        return testo
    righe = []
    for riga in testo.split("\n"):
        parti = riga.split(_RLO)
        vista = parti[0]
        for parte in parti[1:]:
            dentro, _, dopo = parte.partition(_PDF)
            vista += " " + dentro[::-1] + " " + dopo
        righe.append(vista)
    return "\n".join(righe)


def normalizza(testo: str) -> str:
    """Testo normalizzato, pezzi separati da uno spazio (per «prova» e per i log)."""
    return " ".join(pezzi(testo))


def _forma(parola: str) -> str:
    """l e i si confondono (I maiuscola, L minuscola): per il confronto sono la stessa lettera."""
    return parola.replace("l", "i")


def _corse(parola: str) -> tuple[str, tuple[int, ...]]:
    """(lettere senza ripetizioni, quante volte compare ognuna)."""
    lettere: list[str] = []
    conti: list[int] = []
    for c in parola:
        if lettere and lettere[-1] == c:
            conti[-1] += 1
        else:
            lettere.append(c)
            conti.append(1)
    return "".join(lettere), tuple(conti)


def _copre(minimi: tuple[int, ...], conti: tuple[int, ...]) -> bool:
    return all(c >= m for c, m in zip(conti, minimi))


@dataclass(frozen=True)
class Trovato:
    voce: str  # la voce della lista che ha fatto scattare il filtro (normalizzata)
    modo: str  # "parola", "dentro", "separate", "frase"


def pulisci_voce(testo: str) -> tuple[str, ...] | None:
    """Una voce scritta dall'admin -> i suoi pezzi normalizzati, o None se troppo corta."""
    p = tuple(pezzi(testo))
    if sum(len(x) for x in p) < MIN_LETTERE_VOCE:
        return None
    return p


@dataclass(frozen=True)
class Filtro:
    parole: dict  # chiave -> lista di conti minimi
    dentro: tuple  # (chiave, conti minimi, voce)
    frasi: dict  # prima chiave -> lista di liste di (chiave, conti minimi)
    lecite: frozenset
    nomi: dict  # (chiave, conti) -> voce, per il log
    estremi: dict = None  # (prima, ultima lettera) -> lettere delle voci cosi' (per i jolly)

    def vuoto(self) -> bool:
        return not (self.parole or self.dentro or self.frasi)


@lru_cache(maxsize=1)
def carica_base() -> tuple[tuple[tuple[str, bool], ...], tuple[str, ...]]:
    """((voce, dentro), ...) e le parole lecite del file dati."""
    voci: list[tuple[str, bool]] = []
    lecite: list[str] = []
    for riga in FILE_BASE.read_text(encoding="utf-8").splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#"):
            continue
        if riga.startswith("!"):
            lecite.append(riga[1:])
        elif riga.startswith("*"):
            voci.append((riga[1:], True))
        else:
            voci.append((riga, False))
    return tuple(voci), tuple(lecite)


@lru_cache(maxsize=256)
def costruisci(usa_base: bool, proprie: tuple[str, ...] = (), lecite: tuple[str, ...] = ()) -> Filtro:
    """Prepara il filtro: la lista di base (se attiva) piu' le voci del server."""
    voci: list[tuple[str, bool]] = []
    tutte_lecite: list[str] = list(lecite)
    if usa_base:
        base, lecite_base = carica_base()
        voci += list(base)
        tutte_lecite += lecite_base
    voci += [(v, False) for v in proprie]

    parole: dict[str, list[tuple[int, ...]]] = {}
    dentro: list[tuple[str, tuple[int, ...], str]] = []
    frasi: dict[str, list[list[tuple[str, tuple[int, ...]]]]] = {}
    nomi: dict = {}

    def aggiungi_parola(unita: str, voce: str) -> None:
        chiave, conti = _corse(_forma(unita))
        parole.setdefault(chiave, []).append(conti)
        nomi[(chiave, conti)] = voce

    for testo, interno in voci:
        p = pulisci_voce(testo)
        if p is None:
            continue
        unita = "".join(p)
        voce = " ".join(p)
        if len(p) > 1:
            lista = [_corse(_forma(x)) for x in p]
            frasi.setdefault(lista[0][0], []).append(lista)
            nomi[tuple(lista)] = voce
        aggiungi_parola(unita, voce)
        if interno and len(p) == 1 and len(unita) >= MIN_DENTRO:
            chiave, conti = _corse(_forma(unita))
            dentro.append((chiave, conti, voce))

    ok = frozenset(_lecita(x) for x in tutte_lecite) - {""}
    if usa_base and lecite:
        # Una parola lecita del server non puo' essere una voce di base:
        # per quelle c'e' solo l'interruttore con conferma.
        solo_base = Filtro(parole, (), {}, frozenset(), nomi)
        ok -= {x for x in map(_lecita, lecite) if _parola_vietata(solo_base, x.replace(" ", "")) is not None}
    estremi: dict[tuple[str, str], set[str]] = {}
    for chiave in parole:
        for ultima in (chiave[-1], "s"):  # "s": il plurale
            estremi.setdefault((chiave[0], ultima), set()).update(chiave)
    return Filtro(parole, tuple(dentro), frasi, ok, nomi, {k: "".join(sorted(v)) for k, v in estremi.items()})


def _lecita(testo: str) -> str:
    """Una parola lecita normalizzata; di piu' pezzi ("wet back") vale solo divisa cosi'."""
    return " ".join(pezzi(testo))


def _parola_vietata(f: Filtro, p: str) -> str | None:
    """Voce vietata uguale al pezzo (anche con lettere ripetute di piu' o plurale in s)."""
    candidati = [p]
    if len(p) > 3 and p.endswith("s"):
        candidati.append(p[:-1])
    for c in candidati:
        chiave, conti = _corse(_forma(c))
        for minimi in f.parole.get(chiave, ()):
            if len(minimi) == len(conti) and _copre(minimi, conti):
                return f.nomi.get((chiave, minimi), c)
    return None


def _voce_dentro(f: Filtro, p: str) -> str | None:
    """Voce lunga contenuta dentro il pezzo."""
    if len(p) < MIN_DENTRO:
        return None
    chiave_p, conti_p = _corse(_forma(p))
    for chiave, minimi, voce in f.dentro:
        inizio = chiave_p.find(chiave)
        while inizio >= 0:
            if _copre(minimi, conti_p[inizio : inizio + len(chiave)]):
                return voce
            inizio = chiave_p.find(chiave, inizio + 1)
    return None


def _frase(f: Filtro, tokens: list[str], i: int) -> str | None:
    chiave0 = _corse(_forma(tokens[i]))[0]
    for lista in f.frasi.get(chiave0, ()):
        if i + len(lista) > len(tokens):
            continue
        if all(
            (c := _corse(_forma(tokens[i + j])))[0] == k and _copre(m, c[1])
            for j, (k, m) in enumerate(lista)
        ):
            return f.nomi.get(tuple(lista))
    return None


def _separate(f: Filtro, tokens: list[str], i: int) -> str | None:
    """Lettere staccate ("n i g g e r", "n.i.g.g.e.r", "ni gg er"): si uniscono i pezzi corti."""
    unito = tokens[i]
    if len(unito) > 6:
        return None
    for fine in range(i + 1, min(len(tokens), i + MAX_FINESTRA)):
        unito += tokens[fine]
        if len(unito) > MAX_UNITO:
            return None
        finestra = tokens[i : fine + 1]
        if unito in f.lecite or " ".join(finestra) in f.lecite:
            continue
        # Pezzi tutti lunghi: vale solo una parola lunga spezzata in 2 o 3 ("nig ger", "fro cio").
        if min(len(t) for t in finestra) > 2 and (len(finestra) > 3 or len(unito) < 6):
            continue
        voce = _parola_vietata(f, unito)
        if voce is None:
            continue
        # Una voce corta vale solo se ogni pezzo e' una lettera sola ("c o o n").
        if len(voce.replace(" ", "")) <= 4 and any(len(t) > 1 for t in finestra):
            continue
        return voce
    return None


def _jolly(f: Filtro, testo: str) -> str | None:
    """
    Lettere coperte da un simbolo ("n*gger", "f_ggot"): ogni "?" prova le
    lettere delle voci che hanno la stessa prima e ultima lettera del pezzo
    (un pezzo non comincia ne' finisce con un jolly). Nei pezzi lunghi si
    guarda solo attorno ai jolly, per le voci "dentro".
    """
    prove = zone = 0
    lettere_dentro = "".join(sorted({c for chiave, _, _ in f.dentro for c in chiave}))
    for p in _pezzi_con_jolly(testo):
        if p.count("?") > MAX_JOLLY or len(p.replace("?", "")) < 3:
            continue
        if len(p) <= MAX_UNITO:
            forma = _forma(p)
            lettere = f.estremi.get((forma[0], forma[-1]))
            if lettere:
                prove += 1
                if prove > MAX_PEZZI_JOLLY:
                    return None
                if (v := _riempi_e_cerca(f, p, lettere, intera=True)) is not None:
                    return v
            continue
        if not lettere_dentro:
            continue
        for i in (i for i, c in enumerate(p) if c == "?"):
            zona = p[max(0, i - _RAGGIO_JOLLY) : i + _RAGGIO_JOLLY + 1]
            if zona.count("?") > MAX_JOLLY:
                continue
            zone += 1
            if zone > MAX_ZONE_JOLLY:
                return None
            if (v := _riempi_e_cerca(f, zona, lettere_dentro, intera=False)) is not None:
                return v
    return None


def _riempi_e_cerca(f: Filtro, zona: str, lettere: str, intera: bool) -> str | None:
    for candidato in _riempi(zona, lettere):
        if candidato in f.lecite:
            continue
        v = (_parola_vietata(f, candidato) if intera else None) or _voce_dentro(f, candidato)
        if v is not None and len(v.replace(" ", "")) >= 5:
            return v
    return None


def _riempi(zona: str, lettere: str) -> Iterable[str]:
    if "?" not in zona:
        yield zona
        return
    for lettera in lettere:
        yield from _riempi(zona.replace("?", lettera, 1), lettere)


def trova(testo: str, f: Filtro) -> Trovato | None:
    """La prima voce vietata trovata nel testo, o nel testo come si vede, o None."""
    if f.vuoto() or not testo:
        return None
    trovato = _trova_in(testo, f)
    visto = come_si_vede(testo)
    if trovato is None and visto != testo:
        trovato = _trova_in(visto, f)
    return trovato


def _trova_in(testo: str, f: Filtro) -> Trovato | None:
    tokens = pezzi(testo)
    for i, p in enumerate(tokens):
        if p in f.lecite:
            continue
        if (v := _parola_vietata(f, p)) is not None:
            return Trovato(v, "parola")
        if (v := _voce_dentro(f, p)) is not None:
            return Trovato(v, "dentro")
        if f.frasi and (v := _frase(f, tokens, i)) is not None:
            return Trovato(v, "frase")
    for i in range(len(tokens) - 1):
        if (v := _separate(f, tokens, i)) is not None:
            return Trovato(v, "separate")
    if (v := _jolly(f, testo)) is not None:
        return Trovato(v, "censurata")
    return None


def e_voce_di_base(testo: str) -> bool:
    """True se il testo, unito, e' una voce della lista di base (non puo' diventare lecito)."""
    return _parola_vietata(costruisci(True), "".join(pezzi(testo))) is not None


def prime_voci(voci: Iterable[str], massimo: int) -> list[str]:
    """Voci pulite, senza doppioni, con tetto (per salvarle)."""
    viste: list[str] = []
    for v in voci:
        v = v.strip()
        if pulisci_voce(v) is not None and v not in viste:
            viste.append(v)
    return viste[:massimo]


# --- Parola divisa in piu' messaggi brevi dello stesso utente ------------
MAX_LETTERE_BREVE = 8  # un messaggio con piu' lettere di cosi' non e' "breve"
FINESTRA_BREVI = 30.0  # secondi
MAX_SERIE_BREVI = 12
MAX_CHIAVI_BREVI = 2000


class MessaggiBrevi:
    """Ultimi messaggi brevi per (server, canale, utente), con tetto. Solo in memoria."""

    def __init__(self) -> None:
        self._serie: OrderedDict[tuple, list[tuple[float, int, str]]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._serie)

    def aggiungi(self, chiave: tuple, adesso: float, messaggio_id: int, testo: str) -> list[tuple[int, str]]:
        """
        Aggiunge il messaggio e restituisce la serie di brevi ancora nella
        finestra, lui compreso: [(id, testo), ...]. Un messaggio non breve
        chiude la serie e restituisce [].
        """
        if sum(len(p) for p in pezzi(testo)) > MAX_LETTERE_BREVE:
            self._serie.pop(chiave, None)
            return []
        serie = [x for x in self._serie.pop(chiave, []) if adesso - x[0] <= FINESTRA_BREVI]
        serie = (serie + [(adesso, messaggio_id, testo)])[-MAX_SERIE_BREVI:]
        self._serie[chiave] = serie
        while len(self._serie) > MAX_CHIAVI_BREVI:
            self._serie.popitem(last=False)
        return [(m, t) for _, m, t in serie]

    def svuota(self, chiave: tuple) -> None:
        self._serie.pop(chiave, None)
