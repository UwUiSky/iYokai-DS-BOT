"""
core/reputazione_logic.py
=========================
Regole pure della reputazione: chi può dare o ricevere (ruoli richiesti ed esclusi), chi può togliere,
riconoscere «grazie @utente». Nessun accesso a Discord né al database.
Funzioni coperte: LIV-078, LIV-085
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_GRAZIE = re.compile(r"\b(grazie|thanks|thank you|thx|ty)\b", re.IGNORECASE)


def puo_agire(ruoli: Iterable[int], richiesto: int | None, escluso: int | None) -> bool:
    """Ruolo richiesto (se scelto) presente e ruolo escluso (se scelto) assente."""
    ruoli = set(ruoli)
    if richiesto and richiesto not in ruoli:
        return False
    return not (escluso and escluso in ruoli)


def puo_togliere(ruoli: Iterable[int], ruolo_togliere: int | None, e_admin: bool) -> bool:
    """Togliere punti: solo chi ha il ruolo scelto dall'admin (D71); senza ruolo scelto, solo chi gestisce il server."""
    if e_admin:
        return True
    return bool(ruolo_togliere) and ruolo_togliere in set(ruoli)


def contiene_grazie(testo: str) -> bool:
    return bool(_GRAZIE.search(testo or ""))


def bersaglio_del_grazie(testo: str, menzioni: list[tuple[int, bool]], autore_id: int) -> int | None:
    """
    `menzioni`: (id, è_bot) di chi è nominato nel messaggio. Vale solo una persona diversa dall'autore
    e che non sia un bot: con più persone nominate non si dà nulla (nessun dubbio su chi ringrazia).
    """
    if not contiene_grazie(testo):
        return None
    candidati = {i for i, bot in menzioni if not bot and i != autore_id}
    return next(iter(candidati)) if len(candidati) == 1 and len({i for i, _ in menzioni}) == 1 else None
