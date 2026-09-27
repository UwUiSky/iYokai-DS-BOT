"""
core/backup_mirror_logic.py
===============================
Logica pura (nessun I/O, nessun discord.py) del mirroring in tempo
reale dei messaggi verso il server di backup (SPEC.md §11.9).

La regola concordata: MAX 5 messaggi ogni 5 secondi, PER CANALE. Chi
supera il limite non va in coda per essere inviato più tardi — viene
semplicemente SCARTATO (politica di "scarto in burst"): un mirror in
ritardo di minuti non serve a nessuno, e mettere in coda rischierebbe
di accumulare un backlog che non si svuota mai durante un raid/flood
di messaggi, che è probabilmente il momento in cui il mirror serve
di più (per non perdere la cronologia se il server principale viene
cancellato all'improvviso).
"""

from __future__ import annotations

from collections import deque


class MirrorRateLimiter:
    """
    Un contatore a finestra scorrevole per canale. Tiene, per ogni
    canale, i timestamp (float, secondi) degli ultimi messaggi
    inoltrati con successo; quando ne arriva uno nuovo, scarta dalla
    coda quelli più vecchi della finestra e decide se c'è ancora
    spazio.

    Nessun thread/task di pulizia: le code vecchie si auto-svuotano
    al prossimo controllo su quel canale (un canale silenzioso non
    consuma memoria oltre i suoi ultimi messaggi).
    """

    def __init__(self, max_messages: int = 5, window_seconds: float = 5.0) -> None:
        self._max_messages = max_messages
        self._window_seconds = window_seconds
        self._finestre: dict[int, deque[float]] = {}

    def allow(self, channel_id: int, now: float) -> bool:
        """
        True se il messaggio su questo canale può essere inoltrato
        ORA (e in tal caso lo registra); False se va scartato perché
        il canale ha già raggiunto il limite nella finestra corrente.
        """
        finestra = self._finestre.setdefault(channel_id, deque())

        limite_minimo = now - self._window_seconds
        while finestra and finestra[0] <= limite_minimo:
            finestra.popleft()

        if len(finestra) >= self._max_messages:
            return False

        finestra.append(now)
        return True
