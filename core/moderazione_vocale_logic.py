"""
core/moderazione_vocale_logic.py
================================
Regole semplici della moderazione della voce: quale permesso serve, tetto dello spostamento di massa,
scelta «vocale» del mute, durata della sorveglianza. Nessun accesso a Discord.
Funzioni coperte: SPEC §5.1 (MOD-022, 023, 024, 025, 026, 112)
"""

from __future__ import annotations

from datetime import datetime, timedelta

MAX_SPOSTA_TUTTI = 200
MAX_SORVEGLIANZE_SERVER = 50
SORVEGLIANZA_ORE = 24
SCELTE_MUTE = ("niente", "scollega", "sposta")

_PERMESSI = {
    "muta": "mute_members",
    "sordina": "deafen_members",
    "scollega": "move_members",
    "sposta": "move_members",
}


def permesso_per(azione: str) -> str:
    """Il permesso di Discord che serve per l'azione. ValueError se l'azione non esiste."""
    try:
        return _PERMESSI[azione]
    except KeyError:
        raise ValueError(f"azione vocale sconosciuta: {azione}") from None


def da_spostare(membri: list) -> tuple[list, int]:
    """I membri da spostare (al massimo MAX_SPOSTA_TUTTI) e quanti ne restano fuori."""
    scelti = list(membri[:MAX_SPOSTA_TUTTI])
    return scelti, len(membri) - len(scelti)


def stesso_canale(a: int | None, b: int | None) -> bool:
    return a is not None and a == b


def scelta_mute_valida(scelta: str, canale_id: int | None) -> bool:
    """«sposta» vuole un canale; le altre scelte no."""
    if scelta not in SCELTE_MUTE:
        return False
    return scelta != "sposta" or canale_id is not None


def scadenza_sorveglianza(adesso: datetime) -> datetime:
    return adesso + timedelta(hours=SORVEGLIANZA_ORE)
