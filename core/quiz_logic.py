"""
core/quiz_logic.py
==================
Logica pura del quiz (#131, D70, B6): lettura del file di domande (CSV o JSON), controllo dei campi,
mescolata delle risposte, domande integrate, punti di una partita.
Funzioni coperte: SPEC §16 (FUN-001, 004, 005, 006)
Dipende da: data/quiz_base.json
"""

from __future__ import annotations

import csv
import io
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

MAX_BYTE_FILE = 100_000
MAX_DOMANDE_SERVER = 300
MAX_DOMANDA = 200
MAX_RISPOSTA = 80
MAX_TEMA = 40
N_RISPOSTE = 4
LETTERE = "ABCD"
DOMANDE_PARTITA = (3, 15)
PRECISIONE_BOT = 0.6
TEMI_INTEGRATI = ("videogiochi", "cultura", "scienza")
_FILE_BASE = Path(__file__).resolve().parent.parent / "data" / "quiz_base.json"


class FileErrato(ValueError):
    """Il testo dell'errore è la chiave del catalogo da mostrare."""


@dataclass(frozen=True)
class Domanda:
    testo: str
    risposte: tuple[str, ...]  # la prima è la giusta
    tema: str = ""


@dataclass
class DomandaMescolata:
    testo: str
    risposte: tuple[str, ...]
    giusta: int  # indice 0-3 dentro `risposte`


def _pulisci(valore: object) -> str:
    return " ".join(str(valore or "").split())


def controlla(domanda: object, risposte: list[object], tema: object = "") -> Domanda:
    testo, tema_ok = _pulisci(domanda), _pulisci(tema)[:MAX_TEMA]
    ris = tuple(_pulisci(r) for r in risposte)
    if not testo or len(testo) > MAX_DOMANDA:
        raise FileErrato("quiz_file_domanda")
    if len(ris) != N_RISPOSTE or any(not r or len(r) > MAX_RISPOSTA for r in ris):
        raise FileErrato("quiz_file_risposte")
    if len({r.casefold() for r in ris}) != N_RISPOSTE:
        raise FileErrato("quiz_file_doppie")
    return Domanda(testo, ris, tema_ok)


def leggi_file(contenuto: bytes, nome: str) -> list[Domanda]:
    """CSV (domanda, giusta, sbagliata, sbagliata, sbagliata [, tema]) o JSON (elenco di oggetti)."""
    if len(contenuto) > MAX_BYTE_FILE:
        raise FileErrato("quiz_file_grande")
    try:
        testo = contenuto.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FileErrato("quiz_file_illeggibile") from None
    righe: list[Domanda] = []
    if nome.lower().endswith(".json") or testo.lstrip().startswith(("[", "{")):
        try:
            dati = json.loads(testo)
        except ValueError:
            raise FileErrato("quiz_file_illeggibile") from None
        if isinstance(dati, dict):
            dati = dati.get("domande")
        if not isinstance(dati, list):
            raise FileErrato("quiz_file_illeggibile")
        for voce in dati:
            if not isinstance(voce, dict) or not isinstance(voce.get("risposte"), list):
                raise FileErrato("quiz_file_illeggibile")
            righe.append(controlla(voce.get("domanda"), voce["risposte"], voce.get("tema", "")))
    else:
        for riga in csv.reader(io.StringIO(testo)):
            if not any(c.strip() for c in riga):
                continue
            if len(riga) < 1 + N_RISPOSTE:
                raise FileErrato("quiz_file_risposte")
            righe.append(controlla(riga[0], riga[1 : 1 + N_RISPOSTE], riga[5] if len(riga) > 5 else ""))
    if not righe:
        raise FileErrato("quiz_file_vuoto")
    if len(righe) > MAX_DOMANDE_SERVER:
        raise FileErrato("quiz_file_troppe")
    return righe


def mescola(domanda: Domanda, rng: random.Random) -> DomandaMescolata:
    ordine = list(range(N_RISPOSTE))
    rng.shuffle(ordine)
    return DomandaMescolata(domanda.testo, tuple(domanda.risposte[i] for i in ordine), ordine.index(0))


def domande_integrate(tema: str | None = None) -> list[Domanda]:
    """Le domande del file `data/quiz_base.json`; `tema` vuoto = tutte."""
    dati = json.loads(_FILE_BASE.read_text(encoding="utf-8"))
    return [
        Domanda(v["domanda"], tuple(v["risposte"]), t)
        for t, voci in dati.items()
        if not tema or t == tema
        for v in voci
    ]


def scegli(domande: list[Domanda], quante: int, rng: random.Random) -> list[DomandaMescolata]:
    n = max(DOMANDE_PARTITA[0], min(quante, DOMANDE_PARTITA[1]))
    scelte = rng.sample(domande, min(n, len(domande)))
    return [mescola(d, rng) for d in scelte]


@dataclass
class RegoleQuiz:
    punti: int = 10
    secondi: int = 30
    mostra_risposta: bool = True
    bot_gioca: bool = False


@dataclass
class PartitaQuiz:
    """Stato in memoria di una partita: una risposta a testa per domanda, punti per chi indovina."""

    domande: list[DomandaMescolata]
    regole: RegoleQuiz
    indice: int = 0
    risposte: dict[int, int] = field(default_factory=dict)  # user_id -> scelta della domanda corrente
    punti: dict[int, int] = field(default_factory=dict)

    @property
    def corrente(self) -> DomandaMescolata:
        return self.domande[self.indice]

    def rispondi(self, user_id: int, scelta: int) -> bool:
        """Vero se la risposta è nuova. Sincrona: due clic insieme non contano due volte."""
        if user_id in self.risposte or not 0 <= scelta < N_RISPOSTE:
            return False
        self.risposte[user_id] = scelta
        return True

    def chiudi_domanda(self) -> list[int]:
        """Assegna i punti a chi ha indovinato, passa alla domanda dopo. Restituisce chi ha indovinato."""
        giusti = [u for u, s in self.risposte.items() if s == self.corrente.giusta]
        for u in giusti:
            self.punti[u] = self.punti.get(u, 0) + self.regole.punti
        self.risposte = {}
        self.indice += 1
        return giusti

    @property
    def finita(self) -> bool:
        return self.indice >= len(self.domande)


def classifica_partita(punti: dict[int, int]) -> list[tuple[int, int]]:
    return sorted(punti.items(), key=lambda p: (-p[1], p[0]))[:10]


def fai_giocare_bot(partita: PartitaQuiz, bot_id: int, rng: random.Random) -> None:
    """Il bot risponde giusto 6 volte su 10 (si vede in classifica col suo nome)."""
    giusta = partita.corrente.giusta
    if rng.random() < PRECISIONE_BOT:
        partita.rispondi(bot_id, giusta)
    else:
        partita.rispondi(bot_id, rng.choice([i for i in range(N_RISPOSTE) if i != giusta]))
