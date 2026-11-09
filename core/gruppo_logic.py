"""
core/gruppo_logic.py
====================
Logica pura dei giochi di gruppo (#131, D70, B7): battitura (testo, precisione, parole al minuto, immagine del testo)
e acronimi (lettere, controllo delle iniziali, voti anonimi, punti).
Funzioni coperte: SPEC §16 (FUN-010, 011, 012)
Dipende da: data/battitura_testi.json, Pillow
"""

from __future__ import annotations

import difflib
import io
import json
import random
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MAX_TESTO = 300
MIN_TESTO = 20
PAROLE_MIN, PAROLE_MAX = 8, 25
TETTO_TESTI_SERVER = 50
SOGLIA_PRECISIONE = 0.95
_FILE_TESTI = Path(__file__).resolve().parent.parent / "data" / "battitura_testi.json"

LETTERE_ACRONIMO = "ABCDEFGILMNOPRSTUVZ"
MAX_FRASE = 150
MAX_PAROLA = 30
MAX_GIOCATORI = 10
MIN_GIOCATORI_ACRONIMI = 3


def testo_valido(testo: str) -> bool:
    pulito = " ".join(testo.split())
    return MIN_TESTO <= len(pulito) <= MAX_TESTO and PAROLE_MIN <= len(pulito.split()) <= PAROLE_MAX


def testi_integrati() -> list[str]:
    return json.loads(_FILE_TESTI.read_text(encoding="utf-8"))


def _norma(testo: str) -> str:
    return " ".join(testo.split()).casefold()


def precisione(atteso: str, scritto: str) -> float:
    return difflib.SequenceMatcher(None, _norma(atteso), _norma(scritto)).ratio()


def parole_al_minuto(testo: str, secondi: float) -> int:
    return round(len(testo.split()) / max(secondi, 1.0) * 60)


def disegna_testo(testo: str) -> bytes:
    """PNG del testo (non selezionabile, quindi niente copia e incolla); righe a 44 caratteri, qualche disturbo."""
    righe = textwrap.wrap(" ".join(testo.split()), 44) or [""]
    font = ImageFont.load_default(size=30)
    altezza = 40 + 44 * len(righe)
    img = Image.new("RGB", (900, altezza), (32, 34, 37))
    pen = ImageDraw.Draw(img)
    rng = random.Random(testo)
    for _ in range(10):
        pen.line([(rng.randint(0, 900), rng.randint(0, altezza)), (rng.randint(0, 900), rng.randint(0, altezza))], fill=(60, 64, 70), width=2)
    for i, riga in enumerate(righe):
        pen.text((24, 20 + 44 * i), riga, fill=(235, 235, 235), font=font)
    uscita = io.BytesIO()
    img.save(uscita, "PNG", optimize=True)
    return uscita.getvalue()


@dataclass
class PartitaBattitura:
    testo: str
    inizio: datetime
    partecipanti: set[int]
    risultati: dict[int, int] = field(default_factory=dict)  # user_id -> parole al minuto

    def valuta(self, user_id: int, scritto: str, quando: datetime) -> int | None:
        """Parole al minuto se è il primo invio valido (precisione ≥ 0,95) di un partecipante, altrimenti None."""
        if user_id not in self.partecipanti or user_id in self.risultati:
            return None
        secondi = (quando - self.inizio).total_seconds()
        if secondi <= 0 or precisione(self.testo, scritto) < SOGLIA_PRECISIONE:
            return None
        self.risultati[user_id] = parole_al_minuto(self.testo, secondi)
        return self.risultati[user_id]

    @property
    def finita(self) -> bool:
        return len(self.risultati) >= len(self.partecipanti)

    def classifica(self) -> list[tuple[int, int]]:
        return sorted(self.risultati.items(), key=lambda r: (-r[1], r[0]))


# ---------------- acronimi ----------------

def lettere_acronimo(rng: random.Random) -> str:
    return "".join(rng.sample(LETTERE_ACRONIMO, rng.randint(4, 6)))


def frase_valida(frase: str, lettere: str) -> bool:
    parole = frase.split()
    if len(frase) > MAX_FRASE or len(parole) != len(lettere):
        return False
    for parola, lettera in zip(parole, lettere):
        prima = next((c for c in parola if c.isalnum()), "")
        if len(parola) > MAX_PAROLA or prima.upper() != lettera:
            return False
    return True


@dataclass
class PartitaAcronimi:
    giocatori: list[int]
    turni: int
    turno: int = 0
    lettere: str = ""
    frasi: dict[int, str] = field(default_factory=dict)
    ordine: list[int] = field(default_factory=list)  # autori nell'ordine mescolato
    voti: dict[int, int] = field(default_factory=dict)  # votante -> indice
    punti: dict[int, int] = field(default_factory=dict)

    def nuovo_turno(self, rng: random.Random) -> str:
        self.turno += 1
        self.lettere = lettere_acronimo(rng)
        self.frasi, self.ordine, self.voti = {}, [], {}
        return self.lettere

    def invia(self, user_id: int, frase: str) -> str:
        """«ok», «non_giocatore», «gia» o «iniziali». Sincrona: due invii insieme non contano due volte."""
        if user_id not in self.giocatori:
            return "non_giocatore"
        if user_id in self.frasi:
            return "gia"
        frase = " ".join(frase.split())
        if not frase_valida(frase, self.lettere):
            return "iniziali"
        self.frasi[user_id] = frase
        return "ok"

    def apri_voto(self, rng: random.Random) -> list[str]:
        self.ordine = list(self.frasi)
        rng.shuffle(self.ordine)
        return [self.frasi[u] for u in self.ordine]

    def vota(self, votante: int, indice: int) -> str:
        """«ok», «non_giocatore», «proprio», «gia» o «fuori»."""
        if votante not in self.giocatori:
            return "non_giocatore"
        if not 0 <= indice < len(self.ordine):
            return "fuori"
        if self.ordine[indice] == votante:
            return "proprio"
        if votante in self.voti:
            return "gia"
        self.voti[votante] = indice
        return "ok"

    def chiudi_turno(self) -> dict[int, int]:
        """Un punto per voto all'autore. Restituisce i punti di questo turno."""
        turno: dict[int, int] = {}
        for indice in self.voti.values():
            autore = self.ordine[indice]
            turno[autore] = turno.get(autore, 0) + 1
        for u, p in turno.items():
            self.punti[u] = self.punti.get(u, 0) + p
        return turno

    @property
    def finita(self) -> bool:
        return self.turno >= self.turni
