"""
tests/test_security_rate_tracker.py
=======================================
La logica della finestra mobile è già testata a fondo in
tests/test_automod_rate_tracker.py (stessa classe, riusata). Qui solo
il cablaggio: l'istanza dedicata esiste ed è indipendente da quella
di AutoMod.
"""

from datetime import datetime, timezone

from core.automod_rate_tracker import rate_tracker as automod_rate_tracker
from core.security_rate_tracker import GUILD_WIDE_KEY, security_rate_tracker


def test_istanza_dedicata_e_indipendente_da_quella_automod():
    assert security_rate_tracker is not automod_rate_tracker


def test_guild_wide_key_conta_i_join_per_server():
    adesso = datetime.now(timezone.utc)
    security_rate_tracker.record_and_count(123456, GUILD_WIDE_KEY, "joins", adesso, window_seconds=60)
    conteggio = security_rate_tracker.record_and_count(
        123456, GUILD_WIDE_KEY, "joins", adesso, window_seconds=60
    )
    assert conteggio == 2
