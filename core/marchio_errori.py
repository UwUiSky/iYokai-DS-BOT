"""
core/marchio_errori.py
======================
Registro degli ultimi errori del bot con marchio proprio (CFG-032, D111): per ogni server gli ultimi 20, in memoria.
Si salvano solo l'ora, l'origine (un codice fisso), il tipo di errore e, per gli errori di Discord, lo stato HTTP e il
codice. Mai il testo dell'errore, mai il token, mai ID di utenti o messaggi: chi legge il registro è il proprietario del
bot con marchio, e un errore può portare dentro pezzi di richieste.
Funzioni coperte: SPEC §23 (NF-38), catalogo #128 (CFG-032)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

import discord

MAX_ERRORI = 20
ORIGINI = frozenset({"avvio", "login", "comandi", "interazione", "client"})


@dataclass(frozen=True)
class ErroreMarchio:
    quando: datetime
    origine: str
    tipo: str
    dettaglio: str | None = None


_registro: dict[int, deque[ErroreMarchio]] = {}


def _dettaglio(errore: BaseException) -> str | None:
    """Solo numeri: lo stato HTTP e il codice di Discord. Il testo dell'errore non si salva mai."""
    if isinstance(errore, discord.HTTPException):
        codice = getattr(errore, "code", None)
        return f"HTTP {errore.status}" + (f", codice {codice}" if isinstance(codice, int) and codice > 0 else "")
    return None


def registra(guild_id: int, origine: str, errore: BaseException, *, quando: datetime | None = None) -> None:
    """Aggiunge un errore al registro del server. Mai solleva."""
    if origine not in ORIGINI:
        origine = "client"
    voce = ErroreMarchio(quando or datetime.now(timezone.utc), origine, type(errore).__name__[:60], _dettaglio(errore))
    _registro.setdefault(guild_id, deque(maxlen=MAX_ERRORI)).append(voce)


def elenco(guild_id: int) -> list[ErroreMarchio]:
    """Dal più recente al più vecchio."""
    return list(reversed(_registro.get(guild_id, ())))


def svuota(guild_id: int) -> None:
    _registro.pop(guild_id, None)
