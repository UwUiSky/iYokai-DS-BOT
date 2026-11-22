"""
core/music_stato_logic.py
=========================
Titolo del brano come stato dei bot musicali della flotta (MUS-061) con un tetto di aggiornamenti: Discord
permette poche modifiche di stato ogni pochi secondi per connessione, quindi al massimo una ogni
`PAUSA_STATO` secondi per bot, e vale sempre l'ultima richiesta. Mai il bot principale (è in molti server).
Funzioni coperte: SPEC §9 (catalogo MUS-061)
"""

from __future__ import annotations

import time

PAUSA_STATO = 15.0  # secondi tra due cambi di stato dello stesso bot
STATO_MAX = 128  # caratteri del nome di un'attività (Discord)


def titolo_per_stato(titolo: str) -> str:
    """Il titolo adatto a uno stato: una riga sola, senza spazi doppi, al massimo 128 caratteri."""
    pulito = " ".join((titolo or "").split())
    return pulito if len(pulito) <= STATO_MAX else pulito[: STATO_MAX - 1].rstrip() + "…"


class LimiteStato:
    """Tiene l'ultimo valore voluto per ogni bot e dice dopo quanti secondi si può applicare."""

    def __init__(self, pausa: float = PAUSA_STATO, orologio=time.monotonic) -> None:
        self._pausa = pausa
        self._orologio = orologio
        self._ultimo: dict[int, float] = {}
        self.voluto: dict[int, str | None] = {}

    def richiedi(self, chiave: int, valore: str | None) -> float:
        """Registra il valore voluto (None = togli lo stato). 0 = applicalo ora; altrimenti attendi tanto."""
        self.voluto[chiave] = valore
        ultimo = self._ultimo.get(chiave)
        return 0.0 if ultimo is None else max(0.0, self._pausa - (self._orologio() - ultimo))

    def segna_applicato(self, chiave: int) -> None:
        self._ultimo[chiave] = self._orologio()
