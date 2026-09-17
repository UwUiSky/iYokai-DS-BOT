"""
tests/test_memory_guard_logic.py
====================================
Test di core/memory_guard_logic.py — logica pura, nessuna dipendenza
da psutil o Discord.
"""

from datetime import datetime, timedelta, timezone

from core.memory_guard_logic import (
    ALERT_COOLDOWN_SECONDS,
    bytes_to_mb,
    is_over_threshold,
    should_disconnect_voice_client,
    should_send_alert,
)


class TestBytesToMb:
    def test_conversione_corretta(self):
        assert bytes_to_mb(1024 * 1024) == 1.0
        assert bytes_to_mb(10 * 1024 * 1024) == 10.0


class TestIsOverThreshold:
    def test_sotto_soglia(self):
        cento_mb = 100 * 1024 * 1024
        assert is_over_threshold(cento_mb, threshold_mb=512) is False

    def test_sopra_soglia(self):
        mille_mb = 1000 * 1024 * 1024
        assert is_over_threshold(mille_mb, threshold_mb=512) is True

    def test_esattamente_alla_soglia_non_e_sopra(self):
        cinquecentododici_mb = 512 * 1024 * 1024
        assert is_over_threshold(cinquecentododici_mb, threshold_mb=512) is False


class TestShouldSendAlert:
    def test_sotto_soglia_mai_alert(self):
        poco = 100 * 1024 * 1024
        assert should_send_alert(poco, threshold_mb=512, last_alert_at=None) is False

    def test_sopra_soglia_mai_avvisato_prima_manda_alert(self):
        tanto = 1000 * 1024 * 1024
        assert should_send_alert(tanto, threshold_mb=512, last_alert_at=None) is True

    def test_sopra_soglia_ma_avvisato_da_poco_non_manda(self):
        tanto = 1000 * 1024 * 1024
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo_alert = ora - timedelta(minutes=5)
        assert should_send_alert(
            tanto, threshold_mb=512, last_alert_at=ultimo_alert, now=ora
        ) is False

    def test_sopra_soglia_e_cooldown_scaduto_manda_di_nuovo(self):
        tanto = 1000 * 1024 * 1024
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo_alert = ora - timedelta(seconds=ALERT_COOLDOWN_SECONDS + 1)
        assert should_send_alert(
            tanto, threshold_mb=512, last_alert_at=ultimo_alert, now=ora
        ) is True

    def test_esattamente_al_confine_del_cooldown_manda(self):
        tanto = 1000 * 1024 * 1024
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo_alert = ora - timedelta(seconds=ALERT_COOLDOWN_SECONDS)
        assert should_send_alert(
            tanto, threshold_mb=512, last_alert_at=ultimo_alert, now=ora
        ) is True


class TestShouldDisconnectVoiceClient:
    def test_canale_vuoto_va_disconnesso(self):
        assert should_disconnect_voice_client(member_count_excluding_bot=0) is True

    def test_canale_con_persone_non_va_disconnesso(self):
        assert should_disconnect_voice_client(member_count_excluding_bot=1) is False
        assert should_disconnect_voice_client(member_count_excluding_bot=5) is False
