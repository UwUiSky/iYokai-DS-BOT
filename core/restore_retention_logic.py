"""
core/restore_retention_logic.py
===================================
Logica pura per distinguere un KICK da un'uscita spontanea (SPEC.md
§11.11) — Discord non lo dice direttamente: `on_member_remove` si
attiva per QUALSIASI uscita (volontaria, kick, o — separatamente,
`on_member_ban` — ban). Il modo standard per saperlo è controllare
l'audit log del server subito dopo, cercando una voce "kick" che
riguarda quell'utente e che è appena successa.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class _AuditEntryLike(Protocol):
    target_id: int
    created_at: datetime


def was_recently_kicked(
    kick_audit_entries: list[_AuditEntryLike],
    user_id: int,
    now: datetime,
    within_seconds: float = 10.0,
) -> bool:
    """
    True se una delle voci di audit log (già filtrate per azione
    "kick" dal chiamante) riguarda proprio questo utente ed è
    avvenuta negli ultimi `within_seconds` — abbastanza vicino
    all'evento on_member_remove da poter essere ragionevolmente la
    STESSA uscita, non un kick di giorni fa riletto per caso.
    """
    for voce in kick_audit_entries:
        if voce.target_id == user_id and 0 <= (now - voce.created_at).total_seconds() <= within_seconds:
            return True
    return False
