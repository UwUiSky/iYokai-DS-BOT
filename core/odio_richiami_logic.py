"""
core/odio_richiami_logic.py
===========================
Conteggio dei richiami per parole d'odio (D35), in logica pura: N richiami in X
minuti portano al timeout. Solo in memoria, con tetto; non conta il bot.
Funzioni coperte: SPEC §6 (D35)
"""

from __future__ import annotations

from collections import OrderedDict, deque

MAX_CHIAVI = 5000
MAX_RICHIAMI_TENUTI = 50


class ContatoreRichiami:
    def __init__(self, massimo: int = MAX_CHIAVI) -> None:
        self._dati: OrderedDict[tuple[int, int], deque[float]] = OrderedDict()
        self._massimo = massimo

    def __len__(self) -> int:
        return len(self._dati)

    def registra(self, guild_id: int, user_id: int, ora: float, finestra_secondi: float) -> int:
        """Aggiunge un richiamo e dice quanti ce ne sono nella finestra, questo compreso."""
        k = (guild_id, user_id)
        coda = self._dati.pop(k, None) or deque(maxlen=MAX_RICHIAMI_TENUTI)
        while coda and coda[0] <= ora - finestra_secondi:
            coda.popleft()
        coda.append(ora)
        self._dati[k] = coda
        while len(self._dati) > self._massimo:
            self._dati.popitem(last=False)
        return len(coda)

    def azzera(self, guild_id: int, user_id: int) -> None:
        self._dati.pop((guild_id, user_id), None)
