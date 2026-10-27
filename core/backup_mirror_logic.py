"""
core/backup_mirror_logic.py
===============================
Logica pura (nessun I/O, nessun discord.py) del mirroring in tempo
reale dei messaggi verso il server di backup (SPEC.md §11.9).

La regola concordata: MAX 5 messaggi ogni 5 secondi, PER CANALE. Chi
supera il limite aspetta nella coda del canale (core/backup_mirror_dispatch.py)
e parte quando la finestra si libera: l'ordine dei messaggi resta quello
originale.
"""

from __future__ import annotations

import re
from collections import deque

# LIM-38: Discord mostra così i canali che il bot non può leggere.
NOME_CANALE_OFFUSCATO = "___hidden___"

# LIM-27: un nome di webhook non può contenere queste parole.
_PAROLE_VIETATE = re.compile(r"discord|clyde", re.IGNORECASE)
_MAX_NOME_WEBHOOK = 80


def nome_sicuro_per_webhook(nome: str) -> str:
    """
    M 12.7 (LIM-27): il nome del mittente copiato dal mirror non può contenere
    "discord" né "clyde" (in nessuna forma di maiuscole); lunghezza 2-80.
    Le due parole diventano ``disc0rd`` e ``cl1de`` (resta leggibile).
    """
    sostituzioni = {"discord": "disc0rd", "clyde": "cl1de"}
    pulito = _PAROLE_VIETATE.sub(lambda m: sostituzioni[m.group(0).lower()], nome or "")
    pulito = pulito.strip()[:_MAX_NOME_WEBHOOK]
    return pulito if len(pulito) >= 2 else (pulito + "__")[:2]


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
