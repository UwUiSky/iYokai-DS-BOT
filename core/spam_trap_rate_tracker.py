"""
core/spam_trap_rate_tracker.py
==================================
Finestra mobile in memoria per limitare quanti DM di appello dello
spam-trap vengono elaborati per utente (SEC-12) — stessa
implementazione generica di core/automod_rate_tracker.py, ma
un'istanza SEPARATA (vedi il docstring di core/security_rate_tracker.py
per il perché: chiavi che non si mescolano mai per costruzione, ma
un'istanza dedicata evita che un bot con molti DM in arrivo saturi una
cache condivisa con un'altra feature).

Non è per-server (i DM non hanno una guild): si usa `guild_id=0` come
chiave fittizia "globale", stesso trucco già usato da
core/security_rate_tracker.py per il join rate limit.
"""

from __future__ import annotations

from core.automod_rate_tracker import AutomodRateTracker

DM_WIDE_KEY = 0

spam_trap_rate_tracker = AutomodRateTracker()
