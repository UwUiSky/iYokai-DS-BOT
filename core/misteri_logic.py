"""
core/misteri_logic.py
=====================
Misteri nascosti dall'admin: il codice si confronta come impronta (mai in chiaro nel database),
senza badare a maiuscole, accenti e spazi; limiti dei premi; tentativi per persona.
Funzioni coperte: SPEC §25.56 (AI-R-061)
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata

MAX_XP_PREMIO = 500
MAX_MEMBRI_PREMIATI = 200
MAX_TENTATIVI_ORA = 10
ATTESA_TENTATIVI_SECONDI = 5
PREMI = ("xp", "canale")


def normalizza_codice(testo: str) -> str:
    """Minuscole, senza accenti né spazi o segni: «Il Corvo!» e «il  corvo» sono lo stesso codice."""
    senza_accenti = unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", senza_accenti.lower())


def impronta_codice(guild_id: int, testo: str) -> str | None:
    """L'impronta del codice per quel server (None se il codice è vuoto dopo la pulizia)."""
    pulito = normalizza_codice(testo)
    if len(pulito) < 3:
        return None
    return hashlib.sha256(f"mistero:{guild_id}:{pulito}".encode()).hexdigest()


class LimiteTentativi:
    """Quanti tentativi può fare una persona: uno ogni 5 secondi e al massimo 10 all'ora (in memoria)."""

    def __init__(self) -> None:
        self._dati: dict[tuple[int, int], list[float]] = {}

    def consenti(self, guild_id: int, user_id: int, ora: float | None = None) -> str | None:
        """None se può provare, altrimenti il motivo («attesa» o «troppi»)."""
        ora = time.monotonic() if ora is None else ora
        recenti = [t for t in self._dati.get((guild_id, user_id), []) if ora - t < 3600]
        if recenti and ora - recenti[-1] < ATTESA_TENTATIVI_SECONDI:
            self._dati[(guild_id, user_id)] = recenti
            return "attesa"
        if len(recenti) >= MAX_TENTATIVI_ORA:
            self._dati[(guild_id, user_id)] = recenti
            return "troppi"
        recenti.append(ora)
        self._dati[(guild_id, user_id)] = recenti
        if len(self._dati) > 5000:
            self._dati.clear()
        return None
