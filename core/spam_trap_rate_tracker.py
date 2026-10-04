"""
core/spam_trap_rate_tracker.py
==================================
Limite in memoria sui DM di appello dello spam-trap: al massimo un DM
ELABORATO ogni N secondi per utente (SEC-12, BUG-22). I DM scartati
non contano, così chi scrive spesso viene comunque ascoltato appena
l'attesa finisce.
Funzioni coperte: SPEC §7.3
"""

from __future__ import annotations

from datetime import datetime

from core.bounded_cache import BoundedCache


class LimiteDmAppello:
    def __init__(self, max_size: int = 20_000) -> None:
        # user_id → momento dell'ultimo DM elaborato.
        self._ultimo_elaborato: BoundedCache[int, datetime] = BoundedCache(max_size=max_size)

    def __len__(self) -> int:
        return len(self._ultimo_elaborato)

    def puo_elaborare(self, user_id: int, now: datetime, attesa_secondi: int) -> bool:
        """
        True se il DM di questo utente va elaborato adesso; in quel
        caso (e solo in quello) registra `now` come ultimo elaborato.
        """
        ultimo = self._ultimo_elaborato.get(user_id)
        if ultimo is not None and (now - ultimo).total_seconds() < attesa_secondi:
            return False
        self._ultimo_elaborato.set(user_id, now)
        return True

    def azzera(self) -> None:
        """Dimentica tutti gli utenti (usato dai test)."""
        self._ultimo_elaborato.clear()


limite_dm_appello = LimiteDmAppello()
