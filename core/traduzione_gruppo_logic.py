"""
core/traduzione_gruppo_logic.py
===============================
Raccoglie i messaggi consecutivi della stessa persona in un canale con traduzione automatica, così si traduce
una volta sola e con tutto il senso. Nessun accesso a Discord.
Funzioni coperte: SPEC §25.77 (AI-R-084)
"""

from __future__ import annotations

from dataclasses import dataclass, field

ATTESA_SECONDI = 4.0
MAX_MESSAGGI = 6
MAX_CARATTERI = 1500


@dataclass
class RaccoltaMessaggi:
    """Per (canale, autore): i messaggi arrivati durante l'attesa."""

    _aperte: dict = field(default_factory=dict)

    def aggiungi(self, canale: int, autore: int, message_id: int, testo: str) -> bool | None:
        """True se il messaggio apre la raccolta (chi chiama programma la chiusura); False se si accoda;
        None se la raccolta è piena: il messaggio resta fuori e chi chiama lo traduce da solo."""
        chiave = (canale, autore)
        if chiave in self._aperte:
            ids, parti = self._aperte[chiave]
            if len(ids) >= MAX_MESSAGGI or sum(len(p) for p in parti) + len(testo) > MAX_CARATTERI:
                return None
            ids.append(message_id)
            parti.append(testo)
            return False
        self._aperte[chiave] = ([message_id], [testo])
        return True

    def chiudi(self, canale: int, autore: int) -> tuple[list[int], str] | None:
        """(id dei messaggi, testo unito) e la raccolta si svuota."""
        trovata = self._aperte.pop((canale, autore), None)
        if trovata is None:
            return None
        ids, parti = trovata
        return ids, "\n".join(parti)
