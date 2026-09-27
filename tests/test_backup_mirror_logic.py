"""
tests/test_backup_mirror_logic.py
=====================================
Test di MirrorRateLimiter (SPEC.md §11.9) — logica pura, nessun
discord.py, nessun DB: solo il conteggio a finestra scorrevole.
"""

from core.backup_mirror_logic import MirrorRateLimiter


def test_i_primi_5_messaggi_nella_finestra_passano():
    limiter = MirrorRateLimiter(max_messages=5, window_seconds=5.0)
    for i in range(5):
        assert limiter.allow(channel_id=1, now=100.0 + i * 0.1) is True


def test_il_sesto_messaggio_nella_stessa_finestra_viene_scartato():
    limiter = MirrorRateLimiter(max_messages=5, window_seconds=5.0)
    for i in range(5):
        limiter.allow(channel_id=1, now=100.0 + i * 0.1)

    assert limiter.allow(channel_id=1, now=100.6) is False


def test_dopo_la_finestra_il_limite_si_libera():
    limiter = MirrorRateLimiter(max_messages=5, window_seconds=5.0)
    for i in range(5):
        limiter.allow(channel_id=1, now=100.0 + i * 0.1)
    assert limiter.allow(channel_id=1, now=100.6) is False  # ancora scartato

    # Passano 5+ secondi dal PRIMO messaggio della finestra: c'è
    # di nuovo spazio.
    assert limiter.allow(channel_id=1, now=106.0) is True


def test_canali_diversi_hanno_finestre_indipendenti():
    limiter = MirrorRateLimiter(max_messages=5, window_seconds=5.0)
    for i in range(5):
        limiter.allow(channel_id=1, now=100.0 + i * 0.1)

    # Canale 1 è saturo, ma il canale 2 non ha nulla a che fare con lui.
    assert limiter.allow(channel_id=1, now=100.6) is False
    assert limiter.allow(channel_id=2, now=100.6) is True


def test_limiti_personalizzati_vengono_rispettati():
    limiter = MirrorRateLimiter(max_messages=2, window_seconds=1.0)
    assert limiter.allow(channel_id=1, now=0.0) is True
    assert limiter.allow(channel_id=1, now=0.1) is True
    assert limiter.allow(channel_id=1, now=0.2) is False
