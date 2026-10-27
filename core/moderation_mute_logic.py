"""
core/moderation_mute_logic.py
=============================
Regole semplici del mute con ruolo: quali ruoli toglie un hardmute e quando
un mute a tempo è finito.
Funzioni coperte: SPEC §5.1 (MOD-014, 015, 021)
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from core.tempban_logic import RuoloInfo, ruoli_da_salvare, ruoli_da_tenere_in_isolamento

# Un mute a tempo dura al massimo un anno: oltre, si lascia senza fine.
MAX_MUTE_SECONDI = 365 * 86400


def ruoli_hardmute(
    ruoli_membro: Iterable[RuoloInfo], posizione_bot: int, ruolo_mute_id: int
) -> list[int]:
    """
    I ruoli che un hardmute toglie: tutti tranne @everyone, il ruolo mute, quelli
    gestiti da integrazioni e quelli che il bot non può toccare perché non sotto di lui.
    """
    ruoli = list(ruoli_membro)
    restano = set(ruoli_da_tenere_in_isolamento(ruoli, posizione_bot))
    return [i for i in ruoli_da_salvare(ruoli) if i not in restano and i != ruolo_mute_id]


def ruoli_dopo_nuovo_mute(
    stato_precedente_hard: bool, ruoli_precedenti: list[int], ruoli_ora: list[int], hard: bool
) -> list[int]:
    """
    I ruoli da ricordare quando si silenzia chi è già silenziato: se il mute di prima
    era un hardmute i ruoli veri sono quelli salvati allora (ora il membro ne ha pochi).
    """
    if stato_precedente_hard:
        return list(dict.fromkeys(ruoli_precedenti + (ruoli_ora if hard else [])))
    return list(ruoli_ora) if hard else []


def mute_finito(finisce_il: datetime | None, ora: datetime) -> bool:
    """True se il mute aveva una fine ed è passata. Senza fine non finisce da solo."""
    return finisce_il is not None and finisce_il <= ora
