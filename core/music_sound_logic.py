"""
core/music_sound_logic.py
=========================
Effetti sonori in vocale: pausa per utente, scelta del suono dal nome,
valori dell'autocompletamento.
Funzioni coperte: SPEC §23 (NF-35, FUN-078)
Dipende da: niente di Discord (logica pura).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
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


# ---- FUN-078: fermare il suono in corso ----
@dataclass(frozen=True)
class SuonoInCorso:
    """Un suono appena partito in un canale: chi l'ha fatto partire e fino a quando conta come «in corso»."""

    avviato_da: int
    fino_a: float  # secondi dell'orologio monotonico
    da_solo: bool  # il bot è entrato solo per il suono: si può fermare uscendo dal canale


class SuoniInCorso:
    """Il suono in corso per (server, canale): uno solo, l'ultimo partito."""

    def __init__(self, durata: float = ATTESA_USCITA, orologio=time.monotonic) -> None:
        self._durata = durata
        self._orologio = orologio
        self._suoni: dict[tuple[int, int], SuonoInCorso] = {}

    def segna(self, guild_id: int, canale_id: int, avviato_da: int, da_solo: bool) -> None:
        adesso = self._orologio()
        self._suoni = {k: v for k, v in self._suoni.items() if v.fino_a > adesso}  # niente crescita senza fine
        self._suoni[(guild_id, canale_id)] = SuonoInCorso(avviato_da, adesso + self._durata, da_solo)

    def attivo(self, guild_id: int, canale_id: int) -> SuonoInCorso | None:
        suono = self._suoni.get((guild_id, canale_id))
        if suono is None or suono.fino_a <= self._orologio():
            self._suoni.pop((guild_id, canale_id), None)
            return None
        return suono

    def togli(self, guild_id: int, canale_id: int) -> None:
        self._suoni.pop((guild_id, canale_id), None)


def puo_fermare_suono(
    privilegiato: bool, avviato_da: int, utente_id: int, ascoltatori_umani: Iterable[int]
) -> bool:
    """
    FUN-078, stessa logica dei brani della musica: chi l'ha fatto partire; staff e DJ (`privilegiato`) sempre; chiunque
    sia nel canale se chi l'ha avviato non c'è più (nessuno controlla il suono). Chi sta fuori dal canale mai.
    """
    umani = set(ascoltatori_umani)
    if utente_id not in umani:
        return privilegiato or utente_id == avviato_da
    return privilegiato or utente_id == avviato_da or avviato_da not in umani
