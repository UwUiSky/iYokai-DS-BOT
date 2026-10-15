"""
core/music_sound_logic.py
=========================
Effetti sonori in vocale: pausa per utente, scelta del suono dal nome,
valori dell'autocompletamento.
Funzioni coperte: SPEC §23 (NF-35)
Dipende da: niente di Discord (logica pura).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

PAUSA_PER_UTENTE = 10.0  # secondi tra due suoni dello stesso utente
ATTESA_USCITA = 8.0  # secondi: un suono dura al massimo 5,2 s, poi il bot esce
SCELTE_MAX = 25

PREFISSO_SERVER = "s:"
PREFISSO_DISCORD = "d:"


@dataclass(frozen=True)
class Suono:
    """Un suono della soundboard: del server o predefinito di Discord."""

    id: int
    nome: str
    del_server: bool
    emoji: str | None = None

    @property
    def valore(self) -> str:
        return f"{PREFISSO_SERVER if self.del_server else PREFISSO_DISCORD}{self.id}"

    @property
    def etichetta(self) -> str:
        origine = "" if self.del_server else " (Discord)"
        testo = f"{self.emoji} {self.nome}" if self.emoji else self.nome
        return f"{testo}{origine}"[:100]


def scelte(suoni: list[Suono], attuale: str) -> list[tuple[str, str]]:
    """(etichetta, valore) per l'autocompletamento: prima quelli del server, al massimo 25."""
    attuale = (attuale or "").lower().strip()
    ordinati = sorted(suoni, key=lambda s: (not s.del_server, s.nome.lower()))
    return [(s.etichetta, s.valore) for s in ordinati if attuale in s.nome.lower()][:SCELTE_MAX]


def trova(suoni: list[Suono], valore: str) -> Suono | None:
    """Il suono scelto: dal valore dell'autocompletamento o, se scritto a mano, dal nome."""
    valore = (valore or "").strip()
    for s in suoni:
        if s.valore == valore:
            return s
    minuscolo = valore.lower()
    for s in sorted(suoni, key=lambda s: not s.del_server):
        if s.nome.lower() == minuscolo:
            return s
    return None


class PausaUtente:
    """Al massimo un suono ogni PAUSA_PER_UTENTE secondi per utente e server."""

    def __init__(self, pausa: float = PAUSA_PER_UTENTE, orologio=time.monotonic) -> None:
        self._pausa = pausa
        self._orologio = orologio
        self._ultimo: dict[tuple[int, int], float] = {}

    def resta(self, guild_id: int, user_id: int) -> float:
        ultimo = self._ultimo.get((guild_id, user_id))
        if ultimo is None:
            return 0.0
        return max(0.0, self._pausa - (self._orologio() - ultimo))

    def segna(self, guild_id: int, user_id: int) -> None:
        adesso = self._orologio()
        self._ultimo[(guild_id, user_id)] = adesso
        if len(self._ultimo) > 5000:  # niente crescita senza fine
            self._ultimo = {k: v for k, v in self._ultimo.items() if adesso - v < self._pausa}
