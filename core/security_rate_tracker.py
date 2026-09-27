"""
core/security_rate_tracker.py
=================================
Finestra mobile in memoria per la Security Suite (SPEC.md §7.1 join
rate limit, §7.2 rilevamento azioni di massa) — stessa
implementazione generica di core/automod_rate_tracker.py (guild +
"utente" + categoria + finestra), ma un'istanza SEPARATA: le chiavi
delle due feature non si mescolano mai per costruzione (categorie di
stringhe diverse), ma tenerle in cache/istanze distinte evita che un
bot con moltissimi server saturi una singola BoundedCache condivisa
tra due feature indipendenti.

Per il join rate limit (che è per-SERVER, non per singolo utente) si
usa `user_id=0` come chiave fittizia "guild-wide" — non esiste un
vero user_id 0 su Discord (gli ID sono snowflake a 64 bit, sempre
molto più grandi), quindi non c'è rischio di collisione con un utente
reale.
"""

from __future__ import annotations

from core.automod_rate_tracker import AutomodRateTracker

GUILD_WIDE_KEY = 0

security_rate_tracker = AutomodRateTracker()
