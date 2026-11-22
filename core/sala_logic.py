"""
core/sala_logic.py
==================
Regole pure dei giochi a più giocatori con sala d'attesa (/sala): roulette, corsa, lotta, bomba, carte a turni,
bingo, impiccato e quiz. Niente Discord e niente database: ricevono il generatore di numeri casuali, quindi si
provano con un seme. Il banco (roulette) ha il suo vantaggio; negli altri giochi il piatto va tutto al vincitore.
Funzioni coperte: ECO-091, ECO-101, ECO-102, ECO-103, ECO-105, ECO-110, ECO-111, ECO-112, ECO-113, ECO-114
"""

from __future__ import annotations

import json
import pathlib
import random
import unicodedata

from core.coin_games_logic import SCOMMESSE_ROULETTE, numero_vince

MIN_GIOCATORI = 2
MAX_GIOCATORI = 10
DATI = pathlib.Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------- roulette (ECO-091)
def risolvi_roulette(scelte: dict[int, tuple[str, int | None]], puntata: int, rng: random.Random) -> tuple[int, dict[int, int]]:
    """Un solo giro per tutti. Restituisce (numero uscito, monete restituite a ciascuno: 0 se perde)."""
    uscito = rng.randint(0, 36)
    pagamenti = {}
    for utente, (scelta, numero) in scelte.items():
        if scelta not in SCOMMESSE_ROULETTE:
            raise ValueError(f"Scommessa sconosciuta: {scelta}")
        vince = numero_vince(scelta, uscito, numero)
        pagamenti[utente] = puntata * SCOMMESSE_ROULETTE[scelta] if vince else 0
    return uscito, pagamenti


# ---------------------------------------------------------------- corsa (ECO-102, ECO-103)
LUNGHEZZA_CORSA = 30.0


def velocita_animale(livello: int, in_salute: bool) -> float:
    """Da 1,00 a 1,20: l'animale curato e di livello alto parte appena avanti, mai di molto."""
    return 1.0 + (0.02 * min(max(livello, 0), 10) if in_salute else 0.0)


def corsa(velocita: dict[int, float], rng: random.Random) -> tuple[int, list[dict[int, float]]]:
    """Gira a scatti finché qualcuno arriva. Restituisce (vincitore, posizioni dopo ogni scatto)."""
    if not velocita:
        raise ValueError("Nessun corridore.")
    pos = {u: 0.0 for u in velocita}
    storia: list[dict[int, float]] = []
    while True:
        for u, v in velocita.items():
            pos[u] += rng.uniform(1.0, 5.0) * v
        storia.append(dict(pos))
        arrivati = [u for u, p in pos.items() if p >= LUNGHEZZA_CORSA]
        if arrivati:
            migliore = max(pos[u] for u in arrivati)
            return rng.choice([u for u in arrivati if pos[u] == migliore]), storia


# ---------------------------------------------------------------- lotta (ECO-101, ECO-105)
def forza_lottatore(livello_animale: int | None) -> int:
    """50-70: un animale di livello alto ha un po' più possibilità; senza animale combatte uno spirito da 50."""
    return 50 if livello_animale is None else min(70, 50 + 2 * max(0, livello_animale))


def lotta(forza: dict[int, int], rng: random.Random) -> tuple[int, list[int]]:
    """Ogni round esce chi ha il tiro peggiore (tiro = caso 0-100 + forza - 50). (vincitore, eliminati in ordine)."""
    vivi = list(forza)
    eliminati: list[int] = []
    while len(vivi) > 1:
        tiri = {u: rng.random() * 100 + forza[u] - 50 for u in vivi}
        peggiore = min(vivi, key=lambda u: tiri[u])
        vivi.remove(peggiore)
        eliminati.append(peggiore)
    return vivi[0], eliminati


# ---------------------------------------------------------------- bomba (ECO-110)
COLORI_FILI = ("🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "⚪", "🟤", "⚫", "🔶", "🔷")


class Bomba:
    """Si taglia un filo a testa. Uno dei fili è la bomba: chi lo taglia esce. L'ultimo rimasto vince."""

    def __init__(self, giocatori: list[int], rng: random.Random) -> None:
        if len(giocatori) < 2 or len(giocatori) > MAX_GIOCATORI:
            raise ValueError("Servono da 2 a 10 giocatori.")
        self.rng = rng
        self.vivi = list(giocatori)
        self.turno = 0
        self.ultimo_eliminato: int | None = None
        self._nuovo_giro()

    def _nuovo_giro(self) -> None:
        self.fili = list(range(len(self.vivi) + 1))
        self.bomba = self.rng.choice(self.fili)

    @property
    def di_turno(self) -> int:
        return self.vivi[self.turno % len(self.vivi)]

    @property
    def vincitore(self) -> int | None:
        return self.vivi[0] if len(self.vivi) == 1 else None

    def taglia(self, utente: int, filo: int) -> str:
        """'non_turno' | 'filo_no' | 'salvo' | 'esplode' | 'vince'."""
        if self.vincitore is not None or utente != self.di_turno:
            return "non_turno"
        if filo not in self.fili:
            return "filo_no"
        if filo != self.bomba:
            self.fili.remove(filo)
            self.turno = (self.turno + 1) % len(self.vivi)
            return "salvo"
        posto = self.vivi.index(utente)
        self.vivi.remove(utente)
        self.ultimo_eliminato = utente
        if len(self.vivi) == 1:
            return "vince"
        self.turno = posto % len(self.vivi)
        self._nuovo_giro()
        return "esplode"

    def esci(self, utente: int) -> None:
        """Chi non muove in tempo è fuori."""
        if utente in self.vivi and len(self.vivi) > 1:
            posto = self.vivi.index(utente)
            self.vivi.remove(utente)
            if posto < self.turno:
                self.turno -= 1
            self.turno %= len(self.vivi)
            self._nuovo_giro()


# ---------------------------------------------------------------- carte a turni (ECO-111)
SEMI_CARTE = ("🟥", "🟦", "🟩", "🟨")
CARTE_IN_MANO = 5
MAX_MANO = 15
Carta = tuple[int, int]  # (colore 0-3, valore 1-9)


def nome_carta(c: Carta) -> str:
    return f"{SEMI_CARTE[c[0]]}{c[1]}"


def giocabile(carta: Carta, cima: Carta) -> bool:
    return carta[0] == cima[0] or carta[1] == cima[1]


class PartitaCarte:
    """Stesso colore o stesso valore sulla carta in cima. Chi non può pesca e passa. Vince chi finisce le carte."""

    def __init__(self, giocatori: list[int], rng: random.Random) -> None:
        if not 2 <= len(giocatori) <= MAX_GIOCATORI:
            raise ValueError("Servono da 2 a 10 giocatori.")
        self.rng = rng
        self.mazzo: list[Carta] = [(c, v) for c in range(4) for v in range(1, 10)] * 2
        rng.shuffle(self.mazzo)
        self.scarti: list[Carta] = []
        self.ordine = list(giocatori)
        self.mani = {u: [self._prendi() for _ in range(CARTE_IN_MANO)] for u in giocatori}
        self.cima = self._prendi()
        self.turno = 0
        self.vincitore: int | None = None

    def _prendi(self) -> Carta | None:
        if not self.mazzo:
            if len(self.scarti) <= 0:
                return None
            self.mazzo, self.scarti = self.scarti, []
            self.rng.shuffle(self.mazzo)
        return self.mazzo.pop()

    @property
    def di_turno(self) -> int:
        return self.ordine[self.turno % len(self.ordine)]

    def _avanti(self) -> None:
        self.turno = (self.turno + 1) % len(self.ordine)

    def gioca(self, utente: int, indice: int) -> str:
        """'non_turno' | 'non_valida' | 'ok' | 'vince'."""
        if self.vincitore is not None or utente != self.di_turno:
            return "non_turno"
        mano = self.mani[utente]
        if not 0 <= indice < len(mano) or not giocabile(mano[indice], self.cima):
            return "non_valida"
        self.scarti.append(self.cima)
        self.cima = mano.pop(indice)
        if not mano:
            self.vincitore = utente
            return "vince"
        self._avanti()
        return "ok"

    def pesca(self, utente: int) -> Carta | None:
        """Pesca una carta e passa il turno (anche se il mazzo è vuoto)."""
        if self.vincitore is not None or utente != self.di_turno:
            return None
        carta = self._prendi() if len(self.mani[utente]) < MAX_MANO else None
        if carta is not None:
            self.mani[utente].append(carta)
        self._avanti()
        return carta

    def esci(self, utente: int) -> None:
        """Chi non gioca in tempo esce: le sue carte tornano negli scarti. Se resta uno solo, vince."""
        if utente not in self.ordine or len(self.ordine) <= 1:
            return
        posto = self.ordine.index(utente)
        self.scarti.extend(self.mani.pop(utente))
        self.ordine.remove(utente)
        if posto < self.turno:
            self.turno -= 1
        self.turno %= len(self.ordine)
        if len(self.ordine) == 1:
            self.vincitore = self.ordine[0]


# ---------------------------------------------------------------- bingo (ECO-112)
NUMERI_BINGO = 50
RIGHE_CARTELLA, COLONNE_CARTELLA = 3, 5


def cartella_bingo(rng: random.Random) -> list[list[int]]:
    numeri = rng.sample(range(1, NUMERI_BINGO + 1), RIGHE_CARTELLA * COLONNE_CARTELLA)
    return [sorted(numeri[r * COLONNE_CARTELLA:(r + 1) * COLONNE_CARTELLA]) for r in range(RIGHE_CARTELLA)]


def ha_bingo(cartella: list[list[int]], estratti: set[int]) -> bool:
    """Bingo = una riga intera tra i numeri usciti."""
    return any(all(n in estratti for n in riga) for riga in cartella)


def testo_cartella(cartella: list[list[int]], estratti: set[int]) -> str:
    return "\n".join(" ".join(f"[{n:02d}]" if n in estratti else f" {n:02d} " for n in riga) for riga in cartella)


def ordine_estrazione(rng: random.Random) -> list[int]:
    numeri = list(range(1, NUMERI_BINGO + 1))
    rng.shuffle(numeri)
    return numeri


# ---------------------------------------------------------------- impiccato (ECO-113)
ERRORI_MASSIMI = 6
ALFABETO = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PAROLE: list[str] | None = None


def parole_impiccato() -> list[str]:
    global _PAROLE
    if _PAROLE is None:
        dati = json.loads((DATI / "impiccato_it.json").read_text(encoding="utf-8"))
        _PAROLE = [p.upper() for p in dati["parole"] if p.isalpha() and p.isascii() and 4 <= len(p) <= 14]
    return _PAROLE


class Impiccato:
    def __init__(self, parola: str) -> None:
        self.parola = parola.upper()
        self.giuste: set[str] = set()
        self.sbagliate: list[str] = []

    def prova(self, lettera: str) -> str:
        """'gia' | 'giusta' | 'sbagliata' | 'finita'."""
        lettera = lettera.upper()
        if lettera not in ALFABETO or len(lettera) != 1:
            raise ValueError("Una lettera dalla A alla Z.")
        if self.finita:
            return "finita"
        if lettera in self.giuste or lettera in self.sbagliate:
            return "gia"
        if lettera in self.parola:
            self.giuste.add(lettera)
            return "giusta"
        self.sbagliate.append(lettera)
        return "sbagliata"

    @property
    def vinta(self) -> bool:
        return all(c in self.giuste for c in self.parola)

    @property
    def finita(self) -> bool:
        return self.vinta or len(self.sbagliate) >= ERRORI_MASSIMI

    @property
    def mascherata(self) -> str:
        return " ".join(c if c in self.giuste else "\\_" for c in self.parola)


# ---------------------------------------------------------------- quiz (ECO-114)
DOMANDE_PER_PARTITA = 5
_DOMANDE: list[dict] | None = None


def domande_quiz() -> list[dict]:
    """Dal file `data/quiz_it.json`: nessun servizio esterno. Ogni domanda ha 4 risposte e l'indice della giusta."""
    global _DOMANDE
    if _DOMANDE is None:
        dati = json.loads((DATI / "quiz_it.json").read_text(encoding="utf-8"))
        _DOMANDE = [d for d in dati["domande"] if len(d["r"]) == 4 and 0 <= d["g"] < 4]
    return _DOMANDE


def scegli_domande(rng: random.Random, quante: int = DOMANDE_PER_PARTITA) -> list[dict]:
    """Domande senza ripetizioni, con le risposte rimescolate (l'indice giusto si aggiorna)."""
    scelte = []
    for d in rng.sample(domande_quiz(), quante):
        ordine = list(range(4))
        rng.shuffle(ordine)
        scelte.append({"d": d["d"], "r": [d["r"][i] for i in ordine], "g": ordine.index(d["g"]), "c": d.get("c", "")})
    return scelte


def senza_accenti(testo: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", testo) if unicodedata.category(c) != "Mn")
