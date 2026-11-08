"""
core/caso_eventi.py
===================
Un solo punto da cui chi vuole sapere che è nato un caso di moderazione si fa avvisare (AMD-075, evento `caso`):
`moderation_repo.create_case` chiama `notifica`, gli altri moduli si registrano con `registra`. Un ascoltatore
che sbaglia non ferma il caso né gli altri ascoltatori.
Funzioni coperte: SPEC §6 (AMD-075), D63
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

logger = logging.getLogger("iyokai.caso_eventi")

Ascoltatore = Callable[[int, int, int, int, str, str, str | None], Awaitable[None]]
_ascoltatori: list[Ascoltatore] = []


def registra(funzione: Ascoltatore) -> None:
    if funzione not in _ascoltatori:
        _ascoltatori.append(funzione)


def rimuovi(funzione: Ascoltatore) -> None:
    if funzione in _ascoltatori:
        _ascoltatori.remove(funzione)


async def notifica(guild_id: int, case_number: int, user_id: int, moderator_id: int, action_type: str, origine: str,
                   motivo: str | None) -> None:
    for ascoltatore in tuple(_ascoltatori):
        try:
            await ascoltatore(guild_id, case_number, user_id, moderator_id, action_type, origine, motivo)
        except Exception:
            logger.warning("Ascoltatore dei casi in errore nel server %s", guild_id, exc_info=True)
