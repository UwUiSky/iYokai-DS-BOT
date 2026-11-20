"""
core/music_indovina_logic.py
============================
Gioco «indovina la canzone» (MUS-019): risposte normalizzate, estratto breve, punti e tempo di una partita.
Una partita ha da 1 a MAX_ROUND giri, ogni giro un solo punto a chi risponde per primo: i punti non crescono
oltre il numero di giri e non si salvano. Nessun Discord e nessuna rete qui dentro.
Funzioni coperte: SPEC §9 (catalogo MUS-019)
"""

from __future__ import annotations

import difflib
import random
import re
import unicodedata
from dataclasses import dataclass, field

MAX_ROUND = 10
ROUND_PREDEFINITO = 5
ESTRATTO_SECONDI = 15  # quanto suona il brano in ogni giro
TEMPO_ROUND_SECONDI = 30  # tempo per rispondere, dall'inizio dell'estratto
PAUSA_TRA_ROUND_SECONDI = 5
MAX_TENTATIVI_PER_ROUND = 5  # per persona: niente raffica di risposte a caso
PAUSA_TRA_PARTITE_SECONDI = 60  # per server
MAX_PARTITE_INSIEME = 5  # in tutto il bot (una per bot musicale)
RISPOSTA_MAX = 200  # le risposte piu' lunghe si ignorano
SOGLIA_SOMIGLIANZA = 0.88  # solo per titoli di almeno 8 caratteri
INIZIO_MIN_MS = 5_000

_TRA_PARENTESI = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_NON_PAROLE = re.compile(r"[^a-z0-9]+")


def normalizza_risposta(testo: str) -> str:
    """Senza maiuscole, accenti, parentesi (feat, remix...) e punteggiatura; spazi singoli."""
    senza_parentesi = _TRA_PARENTESI.sub(" ", unicodedata.normalize("NFKC", testo or ""))
    scomposto = unicodedata.normalize("NFKD", senza_parentesi.casefold())
    solo_ascii = "".join(c for c in scomposto if unicodedata.category(c) != "Mn").encode("ascii", "ignore").decode()
    return " ".join(_NON_PAROLE.sub(" ", solo_ascii).split())


def risposte_accettate(titolo: str) -> frozenset[str]:
    """Il titolo intero e, se e' scritto «Artista - Titolo», anche ognuna delle due parti (normalizzati)."""
    pezzi = [titolo, *re.split(r"\s[-–—]\s", titolo or "")] if titolo else []
    return frozenset(p for p in (normalizza_risposta(x) for x in pezzi) if p)


def _contiene_parole(tentativo: str, accettata: str) -> bool:
    return f" {accettata} " in f" {tentativo} "


def risposta_corretta(testo: str, accettate: frozenset[str]) -> bool:
    """Uguale, oppure con il titolo dentro (anche con l'artista), oppure con un piccolo errore di battitura."""
    if not testo or len(testo) > RISPOSTA_MAX:
        return False
    tentativo = normalizza_risposta(testo)
    if not tentativo:
        return False
    for accettata in accettate:
        if tentativo == accettata:
            return True
        if len(accettata) >= 4 and len(tentativo) <= 3 * len(accettata) and _contiene_parole(tentativo, accettata):
            return True
        if len(accettata) >= 8 and difflib.SequenceMatcher(None, tentativo, accettata).ratio() >= SOGLIA_SOMIGLIANZA:
            return True
    return False


def inizio_estratto_ms(durata_ms: int, scelta=random.random) -> int:
    """Dove far partire l'estratto: lontano dall'inizio e dalla fine; 0 se il brano e' troppo corto."""
    margine_fine = (ESTRATTO_SECONDI + 5) * 1000
    massimo = durata_ms - margine_fine
    if massimo <= INIZIO_MIN_MS:
        return 0
    return INIZIO_MIN_MS + int(scelta() * (massimo - INIZIO_MIN_MS))


def numero_di_round(richiesti: int, brani_disponibili: int) -> int:
    """Da 1 a MAX_ROUND, mai piu' dei brani (nessun brano ripetuto). 0 se non c'e' nessun brano."""
    if brani_disponibili <= 0:
        return 0
    return max(1, min(int(richiesti), MAX_ROUND, brani_disponibili))


@dataclass
class Partita:
    guild_id: int
    canale_testo_id: int
    host_id: int
    round_totali: int
    round_corrente: int = 0
    punteggi: dict[int, int] = field(default_factory=dict)
    risposte: frozenset[str] = frozenset()
    aperto: bool = False
    _tentativi: dict[int, int] = field(default_factory=dict)

    def apri_round(self, titolo: str) -> None:
        self.round_corrente += 1
        self.risposte = risposte_accettate(titolo)
        self._tentativi = {}
        self.aperto = True

    def chiudi_round(self) -> None:
        self.aperto = False

    def ultimo_round(self) -> bool:
        return self.round_corrente >= self.round_totali

    def prova(self, utente_id: int, testo: str) -> bool:
        """Vero se `utente_id` ha indovinato per primo il giro aperto (e prende 1 punto, una sola volta per giro)."""
        if not self.aperto:
            return False
        fatti = self._tentativi.get(utente_id, 0)
        if fatti >= MAX_TENTATIVI_PER_ROUND:
            return False
        self._tentativi[utente_id] = fatti + 1
        if not risposta_corretta(testo, self.risposte):
            return False
        self.aperto = False  # il primo che indovina chiude il giro: nessun doppio punto
        self.punteggi[utente_id] = self.punteggi.get(utente_id, 0) + 1
        return True

    def classifica(self, limite: int = 10) -> list[tuple[int, int]]:
        return sorted(self.punteggi.items(), key=lambda kv: (-kv[1], kv[0]))[:limite]


# Server dove una partita e' in corso: gli altri comandi (titolo in corso, coda, annunci, riserva) non rivelano i brani.
_in_gioco: set[int] = set()


def in_gioco(guild_id: int) -> bool:
    return guild_id in _in_gioco


def segna_in_gioco(guild_id: int) -> None:
    _in_gioco.add(guild_id)


def togli_in_gioco(guild_id: int) -> None:
    _in_gioco.discard(guild_id)


def partite_in_corso() -> int:
    return len(_in_gioco)
