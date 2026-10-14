"""
core/activity_stats_logic.py
============================
Statistiche di attività (NF-25, #96): aggregazione in memoria per giorno,
sessioni vocali, esclusioni e calcolo dei ruoli per attività.
Niente Discord e niente database: il cog legge gli eventi, qui si somma;
il repository scrive un lotto ogni minuto (costo basso, nessuna riga per
messaggio). Funzioni coperte: SPEC §23 (NF-25)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

MAX_CHIAVI_BUFFER = 20000      # oltre, il cog scrive subito il lotto
MAX_SECONDI_SESSIONE = 86400   # una sessione non vale più di un giorno tra due controlli
MAX_REGOLE_PER_SERVER = 10
MAX_CAMBI_PER_GIRO = 25        # ruoli dati/tolti per regola a ogni giro (limiti di Discord)
GIORNI_CONSERVAZIONE = 90

METRICHE = ("messages", "voice_minutes")


def _utc(quando: datetime) -> datetime:
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


class ActivityBuffer:
    """Somme in memoria: [messaggi, secondi_vocale] per canale, membro e ora."""

    def __init__(self) -> None:
        self._canali: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
        self._membri: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
        self._ore: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])

    @property
    def pieno(self) -> bool:
        return len(self._canali) + len(self._membri) + len(self._ore) >= MAX_CHIAVI_BUFFER

    def _somma(self, guild_id: int, canale_id: int, utente_id: int, quando: datetime, i: int, n: int) -> None:
        quando = _utc(quando)
        giorno = quando.date()
        self._canali[(guild_id, giorno, canale_id)][i] += n
        self._membri[(guild_id, giorno, utente_id)][i] += n
        self._ore[(guild_id, giorno, quando.hour)][i] += n

    def add_message(self, guild_id: int, canale_id: int, utente_id: int, quando: datetime) -> None:
        self._somma(guild_id, canale_id, utente_id, quando, 0, 1)

    def add_voice(self, guild_id: int, canale_id: int, utente_id: int, secondi: int, quando: datetime) -> None:
        if secondi > 0:
            self._somma(guild_id, canale_id, utente_id, quando, 1, int(secondi))

    def restore(self, canali: dict, membri: dict, ore: dict) -> None:
        """Rimette in coda un lotto che non è stato scritto."""
        for mio, altro in ((self._canali, canali), (self._membri, membri), (self._ore, ore)):
            for chiave, (m, v) in altro.items():
                mio[chiave][0] += m
                mio[chiave][1] += v

    def drain(self) -> tuple[dict, dict, dict]:
        out = (dict(self._canali), dict(self._membri), dict(self._ore))
        self._canali.clear()
        self._membri.clear()
        self._ore.clear()
        return out


class VoiceTracker:
    """Chi è in vocale e da quando. `tick` accredita il tempo passato e riparte da adesso."""

    def __init__(self) -> None:
        self._sessioni: dict[tuple[int, int], list] = {}

    def entra(self, guild_id: int, canale_id: int, utente_id: int, quando: datetime) -> None:
        self._sessioni[(guild_id, utente_id)] = [canale_id, _utc(quando)]

    def esce(self, guild_id: int, utente_id: int, quando: datetime) -> list[tuple[int, int, int, int]]:
        sessione = self._sessioni.pop((guild_id, utente_id), None)
        if sessione is None:
            return []
        return self._credito(guild_id, utente_id, sessione, _utc(quando))

    @staticmethod
    def _credito(guild_id, utente_id, sessione, ora) -> list[tuple[int, int, int, int]]:
        secondi = min(int((ora - sessione[1]).total_seconds()), MAX_SECONDI_SESSIONE)
        sessione[1] = ora
        return [(guild_id, utente_id, sessione[0], secondi)] if secondi > 0 else []

    def tick(self, quando: datetime) -> list[tuple[int, int, int, int]]:
        ora = _utc(quando)
        crediti: list[tuple[int, int, int, int]] = []
        for (guild_id, utente_id), sessione in self._sessioni.items():
            crediti += self._credito(guild_id, utente_id, sessione, ora)
        return crediti

    def __len__(self) -> int:
        return len(self._sessioni)


def escluso(canale_id: int, ruoli_utente, canali_ignorati, ruoli_ignorati) -> bool:
    return canale_id in set(canali_ignorati) or bool(set(ruoli_utente) & set(ruoli_ignorati))


def ruoli_da_aggiornare(
    eleggibili: set[int], possessori: set[int], rimuovi: bool, limite: int = MAX_CAMBI_PER_GIRO
) -> tuple[set[int], set[int]]:
    """(chi riceve il ruolo, a chi si toglie): al massimo `limite` per parte, ordine stabile."""
    dare = sorted(eleggibili - possessori)[:limite]
    togliere = sorted(possessori - eleggibili)[:limite] if rimuovi else []
    return set(dare), set(togliere)


def per_giorno_settimana(per_giorno: dict[date, int]) -> list[int]:
    """Somma per giorno della settimana, lunedì = posizione 0."""
    totali = [0] * 7
    for giorno, valore in per_giorno.items():
        totali[giorno.weekday()] += valore
    return totali
