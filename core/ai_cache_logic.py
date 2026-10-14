"""
core/ai_cache_logic.py
======================
Memoria delle risposte già date: chiave per domande uguali, somiglianza
per domande molto simili, scadenza. Ciò che nasce dai messaggi di un
server resta in quel server; ciò che l'AI scrive da zero va nella
libreria comune (ambito 0) e si riusa ovunque (D19).
Funzioni coperte: SPEC §25.2, §25.11, §25.80 (AI-R-004, AI-R-005, AI-R-087)
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict
from dataclasses import dataclass

LIBRERIA_COMUNE = 0  # ambito dei contenuti senza messaggi di utenti
# Lavori dove una parola cambia tutto ("non"): si riusa solo la risposta al testo uguale.
TIPI_SOLO_UGUALI = frozenset({"traduzione", "giudizio", "codice", "confronto"})
SOGLIA_SIMILE = 0.85
MAX_VOCI = 2000
DURATA_SECONDI = 7 * 24 * 3600

_NON_PAROLA = re.compile(r"[^\w]+", re.UNICODE)


def normalizza(testo: str) -> str:
    """Minuscole, senza punteggiatura, spazi singoli: 'Ciao, come va?' == 'ciao come va'."""
    return " ".join(_NON_PAROLA.sub(" ", testo.lower()).split())


def chiave(tipo: str, istruzioni: str, testo: str) -> str:
    grezzo = f"{tipo}\x1f{normalizza(istruzioni)}\x1f{normalizza(testo)}"
    return hashlib.sha256(grezzo.encode("utf-8")).hexdigest()


def somiglianza(a: str, b: str) -> float:
    """Parole in comune su parole totali (0–1), sul testo normalizzato."""
    pa, pb = set(normalizza(a).split()), set(normalizza(b).split())
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


def ambito(guild_id: int | None, messaggi_utenti: bool) -> int:
    """Dove vale una risposta: nel server se viene da messaggi di utenti, altrimenti ovunque."""
    if messaggi_utenti and guild_id:
        return guild_id
    return LIBRERIA_COMUNE


@dataclass
class _Voce:
    tipo: str
    istruzioni: str
    testo: str
    risposta: str
    scade: float


class CacheAI:
    """Cache in memoria (LRU con scadenza). Il database tiene la copia durevole."""

    def __init__(self, max_voci: int = MAX_VOCI, durata: float = DURATA_SECONDI) -> None:
        self._voci: OrderedDict[tuple[int, str], _Voce] = OrderedDict()
        self._max = max_voci
        self._durata = durata

    def __len__(self) -> int:
        return len(self._voci)

    def metti(self, amb: int, tipo: str, istruzioni: str, testo: str, risposta: str, ora: float | None = None) -> str:
        ora = time.monotonic() if ora is None else ora
        k = chiave(tipo, istruzioni, testo)
        self._voci[(amb, k)] = _Voce(tipo, normalizza(istruzioni), normalizza(testo), risposta, ora + self._durata)
        self._voci.move_to_end((amb, k))
        while len(self._voci) > self._max:
            self._voci.popitem(last=False)
        return k

    def trova(
        self, amb: int, tipo: str, istruzioni: str, testo: str, ora: float | None = None, soglia: float = SOGLIA_SIMILE
    ) -> str | None:
        """
        Risposta per la stessa domanda o per una molto simile (stesse istruzioni, stesso tipo).
        Per i tipi di `TIPI_SOLO_UGUALI` solo la stessa domanda.
        """
        ora = time.monotonic() if ora is None else ora
        k = chiave(tipo, istruzioni, testo)
        voce = self._voci.get((amb, k))
        if voce is not None and voce.scade > ora:
            self._voci.move_to_end((amb, k))
            return voce.risposta
        if tipo in TIPI_SOLO_UGUALI:
            return None
        istr = normalizza(istruzioni)
        migliore, punteggio = None, soglia
        for (a, _), v in reversed(self._voci.items()):
            if a != amb or v.tipo != tipo or v.istruzioni != istr or v.scade <= ora:
                continue
            s = somiglianza(v.testo, testo)
            if s >= punteggio:
                migliore, punteggio = v.risposta, s
        return migliore

    def svuota_ambito(self, amb: int) -> None:
        """Tolto un server (cancellazione dei dati): via anche le sue risposte in memoria."""
        for k in [k for k in self._voci if k[0] == amb]:
            del self._voci[k]
