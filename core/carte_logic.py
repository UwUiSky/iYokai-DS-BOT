"""
core/carte_logic.py
===================
Logica pura del gioco di carte «Frasi a sorpresa» (#131, D70, B8): pacchetti di carte originali, mani di 7 carte,
carta nera con uno spazio, scelta del giudice o voto, punti. Le carte sono scritte per iYokai (nessuna carta di
altri giochi). Il pacchetto «adulti» è spento di base e si usa solo in un canale con limite d'età.
Funzioni coperte: SPEC §16 (FUN-007, 008)
Dipende da: data/carte/<pacchetto>.json
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent.parent / "data" / "carte"
PACCHETTI = ("base", "nerd", "gamer")
PACCHETTO_ADULTI = "adulti"
PACCHETTI_DI_BASE = ",".join(PACCHETTI)
SPAZIO = "____"
CARTE_IN_MANO = 7
MIN_GIOCATORI, MAX_GIOCATORI = 3, 10
PUNTI_MIN, PUNTI_MAX = 2, 10
MAX_ROUND = 30
MODI = ("giudice", "voto")


def carica_pacchetto(nome: str) -> tuple[list[str], list[str]]:
    dati = json.loads((CARTELLA / f"{nome}.json").read_text(encoding="utf-8"))
    return list(dati["nere"]), list(dati["bianche"])


def pacchetti_attivi(scelta: str, adulti_ok: bool, canale_con_limite_eta: bool) -> list[str]:
    """I pacchetti da usare: `scelta` può essere un nome o «tutti». Gli adulti solo se il server li ha accesi E il canale ha il limite d'età."""
    consentiti = list(PACCHETTI)
    if adulti_ok and canale_con_limite_eta:
        consentiti.append(PACCHETTO_ADULTI)
    if scelta == "tutti":
        return consentiti
    return [scelta] if scelta in consentiti else []


def mazzi(nomi: list[str], rng: random.Random) -> tuple[list[str], list[str]]:
    nere: list[str] = []
    bianche: list[str] = []
    for nome in nomi:
        n, b = carica_pacchetto(nome)
        nere += n
        bianche += b
    rng.shuffle(nere)
    rng.shuffle(bianche)
    return nere, bianche


def bianche_necessarie(giocatori: int) -> int:
    return giocatori * (CARTE_IN_MANO + 1)


def riempi(nera: str, bianca: str) -> str:
    return nera.replace(SPAZIO, f"**{bianca}**", 1)


def pacchetti_dal_testo(testo: str) -> list[str]:
    return [p for p in testo.split(",") if p in PACCHETTI]


@dataclass
class PartitaCarte:
    giocatori: list[int]
    vittoria: int
    modo: str
    nere: list[str]
    mazzo: list[str]
    rng: random.Random
    mani: dict[int, list[str]] = field(default_factory=dict)
    scarti: list[str] = field(default_factory=list)
    round: int = 0
    nera: str = ""
    giudice: int = 0
    giocate: dict[int, str] = field(default_factory=dict)
    ordine: list[int] = field(default_factory=list)
    voti: dict[int, int] = field(default_factory=dict)
    scelta_giudice: int | None = None
    punti: dict[int, int] = field(default_factory=dict)

    def _pesca(self) -> str:
        if not self.mazzo:
            self.mazzo, self.scarti = self.scarti, []
            self.rng.shuffle(self.mazzo)
        return self.mazzo.pop()

    def nuovo_round(self) -> str:
        self.round += 1
        self.nera = self.nere.pop(0)
        self.nere.append(self.nera)  # quando finiscono, si ricomincia
        self.giudice = self.giocatori[(self.round - 1) % len(self.giocatori)] if self.modo == "giudice" else 0
        self.giocate, self.ordine, self.voti, self.scelta_giudice = {}, [], {}, None
        for u in self.giocatori:
            mano = self.mani.setdefault(u, [])
            while len(mano) < CARTE_IN_MANO:
                mano.append(self._pesca())
        return self.nera

    def chi_gioca(self) -> list[int]:
        return [u for u in self.giocatori if u != self.giudice]

    def gioca(self, user_id: int, indice: int) -> str:
        """«ok», «non_giocatore», «giudice», «gia» o «fuori». Sincrona: due clic insieme non giocano due carte."""
        if user_id not in self.giocatori:
            return "non_giocatore"
        if user_id == self.giudice:
            return "giudice"
        if user_id in self.giocate:
            return "gia"
        mano = self.mani[user_id]
        if not 0 <= indice < len(mano):
            return "fuori"
        carta = mano.pop(indice)
        self.giocate[user_id] = carta
        self.scarti.append(carta)
        return "ok"

    def apri_scelta(self) -> list[str]:
        self.ordine = list(self.giocate)
        self.rng.shuffle(self.ordine)
        return [self.giocate[u] for u in self.ordine]

    def scegli(self, user_id: int, indice: int) -> str:
        """Giudice: sceglie lui. Voto: un voto a testa, non per sé. «ok», «non_giocatore», «non_giudice», «proprio», «gia», «fuori»."""
        if user_id not in self.giocatori:
            return "non_giocatore"
        if not 0 <= indice < len(self.ordine):
            return "fuori"
        if self.modo == "giudice":
            if user_id != self.giudice:
                return "non_giudice"
            if self.scelta_giudice is not None:
                return "gia"
            self.scelta_giudice = indice
            return "ok"
        if self.ordine[indice] == user_id:
            return "proprio"
        if user_id in self.voti:
            return "gia"
        self.voti[user_id] = indice
        return "ok"

    def votanti(self) -> int:
        return 1 if self.modo == "giudice" else len(self.giocatori)

    def scelte_fatte(self) -> int:
        return int(self.scelta_giudice is not None) if self.modo == "giudice" else len(self.voti)

    def chiudi_round(self) -> int | None:
        """Assegna il punto e restituisce il vincitore del round (None se nessuno ha giocato o votato)."""
        if not self.ordine:
            return None
        if self.modo == "giudice":
            if self.scelta_giudice is None:
                return None
            vincitore = self.ordine[self.scelta_giudice]
        else:
            if not self.voti:
                return None
            conta: dict[int, int] = {}
            for i in self.voti.values():
                conta[i] = conta.get(i, 0) + 1
            migliore = max(conta.values())
            vincitore = self.ordine[self.rng.choice([i for i, n in conta.items() if n == migliore])]
        self.punti[vincitore] = self.punti.get(vincitore, 0) + 1
        return vincitore

    def finita(self) -> bool:
        return self.round >= MAX_ROUND or any(p >= self.vittoria for p in self.punti.values())
