"""
core/voice_saluti_logic.py
==========================
Saluti a voce: riconoscimento del saluto con regole (senza AI), raccolta di chi saluta in pochi secondi per rispondere
con un solo vocale, pausa per canale, frasi fisse. Solo nei canali scelti dall'admin.
Funzioni coperte: SPEC §25.105 (AI-R-112)
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from core.voice_text_logic import nome_pronunciabile

ATTESA_RACCOLTA = 6.0      # secondi: chi saluta in questo tempo riceve una risposta sola
PAUSA_CANALE = timedelta(minutes=2)
MAX_NOMI = 3
MAX_LUNGHEZZA_SALUTO = 40

_SALUTI = (
    ("buongiorno", re.compile(r"^(buon\s*giorno|buongiorno|good morning)\b", re.I)),
    ("buon pomeriggio", re.compile(r"^(buon\s*pomeriggio|good afternoon)\b", re.I)),
    ("buonasera", re.compile(r"^(buona\s*sera|buonasera|good evening)\b", re.I)),
    ("buonanotte", re.compile(r"^(buona\s*notte|buonanotte|good night)\b", re.I)),
    ("ciao", re.compile(r"^(ciao|salve|hey|hello|hi|ehi)\b", re.I)),
)
_RISPOSTE = {
    "buongiorno": ("Buongiorno{chi}!", "Ehi, buongiorno{chi}!"),
    "buon pomeriggio": ("Buon pomeriggio{chi}!",),
    "buonasera": ("Buonasera{chi}!", "Ehi, buonasera{chi}!"),
    "buonanotte": ("Buonanotte{chi}, a domani!",),
    "ciao": ("Ciao{chi}!", "Ehi, ciao{chi}!"),
}


def riconosci_saluto(testo: str) -> str | None:
    """Il saluto se il messaggio è davvero solo un saluto (breve, a inizio frase)."""
    pulito = (testo or "").strip()
    if not pulito or len(pulito) > MAX_LUNGHEZZA_SALUTO or "http" in pulito.lower():
        return None
    for nome, regola in _SALUTI:
        if regola.match(pulito):
            return nome
    return None


def elenco_nomi(nomi: list[str]) -> str:
    if not nomi:
        return ""
    if len(nomi) == 1:
        return nomi[0]
    return ", ".join(nomi[:-1]) + " e " + nomi[-1]


def frase_saluto(saluto: str, nomi_grezzi: list[str], rng=random) -> tuple[str, bool]:
    """(frase, fissa): senza nomi pronunciabili è una frase fissa («a tutti»), che resta in cache per sempre."""
    nomi = [n for n in (nome_pronunciabile(x) for x in nomi_grezzi) if n][:MAX_NOMI]
    scelta = rng.choice(_RISPOSTE[saluto])
    if not nomi:
        return scelta.format(chi=" a tutti"), True
    return scelta.format(chi=", " + elenco_nomi(nomi)), False


@dataclass
class RaccoltaSaluti:
    """Per canale: chi ha salutato nell'attesa e quando c'è stata l'ultima risposta."""

    _aperti: dict = field(default_factory=dict)
    _ultima: dict = field(default_factory=dict)

    def aggiungi(self, canale: int, saluto: str, nome: str, adesso: datetime) -> bool:
        """True se questo saluto apre la raccolta (chi chiama deve programmare la chiusura). False se si accoda o c'è la pausa."""
        ultima = self._ultima.get(canale)
        if canale not in self._aperti and ultima is not None and adesso - ultima < PAUSA_CANALE:
            return False
        if canale in self._aperti:
            self._aperti[canale][1].append(nome)
            return False
        self._aperti[canale] = (saluto, [nome])
        return True

    def chiudi(self, canale: int, adesso: datetime) -> tuple[str, list[str]] | None:
        raccolta = self._aperti.pop(canale, None)
        if raccolta is not None:
            self._ultima[canale] = adesso
        return raccolta
