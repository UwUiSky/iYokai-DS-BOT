"""
core/bot_stats.py
====================
Contatori a finestra scorrevole per le statistiche globali (SPEC.md
§17.8): comandi/minuto ed errori/minuto. Logica pura — solo
timestamp e conteggi, nessuna dipendenza da discord.py. Due istanze
condivise in fondo al file, sul modello di core/premium.py (registry)
e core/scheduler.py (scheduler): un unico contatore per tutto il bot,
non uno per cog.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

DEFAULT_WINDOW_SECONDS = 60


class RollingCounter:
    """
    Conta eventi (comandi, errori) nella finestra temporale più
    recente. Non un contatore cumulativo dall'avvio del bot — quello
    direbbe "quanti comandi in totale", questo dice "quanto è
    attivo il bot ADESSO", più utile per un pannello di monitoraggio.
    """

    def __init__(self, window_seconds: int = DEFAULT_WINDOW_SECONDS) -> None:
        self._window_seconds = window_seconds
        self._timestamps: deque[datetime] = deque()

    def record(self, at: datetime | None = None) -> None:
        self._timestamps.append(at or datetime.now(timezone.utc))

    def count_in_window(self, now: datetime | None = None) -> int:
        """
        Filtra e pota tutti i timestamp scaduti, non solo quelli in
        testa alla coda — non presume che gli inserimenti arrivino in
        ordine cronologico (in produzione lo sono sempre, dato che
        record() usa "adesso", ma un test con inserimenti fuori
        ordine ha rivelato che "pota solo da sinistra" si ferma al
        primo timestamp ancora valido e lascia scaduti più indietro
        nella coda non rimossi — bug reale trovato scrivendo il test,
        non ipotizzato).
        """
        now = now or datetime.now(timezone.utc)
        soglia = now - timedelta(seconds=self._window_seconds)
        self._timestamps = deque(t for t in self._timestamps if t >= soglia)
        return len(self._timestamps)


command_counter = RollingCounter()
error_counter = RollingCounter()
