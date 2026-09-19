"""
tests/test_memory_guard_logic.py
====================================
Test di core/memory_guard_logic.py — logica pura, nessuna dipendenza
da psutil o Discord.
"""

from datetime import datetime, timedelta, timezone

from core.memory_guard_logic import (
    ALERT_COOLDOWN_SECONDS,
    MemoryTier,
    bytes_to_mb,
    classify_memory_tier,
    is_over_threshold,
    should_disconnect_voice_client,
    should_force_gc,
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
        # 550MB su una soglia di 512MB: livello CRITICAL (tra 100% e
        # 130% della soglia), dove il cooldown si applica ancora — a
        # differenza di EMERGENCY (oltre 130%), che lo bypassa sempre
        # per progetto (vedi core/memory_guard_logic.py).
        poco_sopra = 550 * 1024 * 1024
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo_alert = ora - timedelta(minutes=5)
        assert should_send_alert(
            poco_sopra, threshold_mb=512, last_alert_at=ultimo_alert, now=ora
        ) is False

    def test_sopra_soglia_e_cooldown_scaduto_manda_di_nuovo(self):
        # 550MB (livello CRITICAL, non EMERGENCY): qui il cooldown
        # conta davvero, a differenza di un valore >=130% che
        # darebbe True comunque per via del bypass EMERGENCY.
        poco_sopra = 550 * 1024 * 1024
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo_alert = ora - timedelta(seconds=ALERT_COOLDOWN_SECONDS + 1)
        assert should_send_alert(
            poco_sopra, threshold_mb=512, last_alert_at=ultimo_alert, now=ora
        ) is True

    def test_esattamente_al_confine_del_cooldown_manda(self):
        poco_sopra = 550 * 1024 * 1024
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo_alert = ora - timedelta(seconds=ALERT_COOLDOWN_SECONDS)
        assert should_send_alert(
            poco_sopra, threshold_mb=512, last_alert_at=ultimo_alert, now=ora
        ) is True

    def test_emergency_bypassa_sempre_il_cooldown(self):
        # Il caso che il cambio a quattro livelli introduce davvero:
        # 1000MB su una soglia di 512MB è oltre il 130% (EMERGENCY) —
        # deve avvisare SEMPRE, anche un secondo dopo l'alert precedente.
        tanto = 1000 * 1024 * 1024
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        alert_un_secondo_fa = ora - timedelta(seconds=1)
        assert should_send_alert(
            tanto, threshold_mb=512, last_alert_at=alert_un_secondo_fa, now=ora
        ) is True


class TestClassifyMemoryTier:
    SOGLIA = 512  # MB

    def test_ben_sotto_soglia_e_normal(self):
        assert classify_memory_tier(100 * 1024 * 1024, self.SOGLIA) == MemoryTier.NORMAL

    def test_appena_sotto_warning_e_normal(self):
        appena_sotto = int(self.SOGLIA * 0.69 * 1024 * 1024)
        assert classify_memory_tier(appena_sotto, self.SOGLIA) == MemoryTier.NORMAL

    def test_al_70_percento_e_warning(self):
        # Un valore ESATTAMENTE al 70% è un confine in virgola mobile
        # fragile da testare (bytes_to_mb() fa un giro byte->MB con
        # arrotondamento) — un pelo sopra è altrettanto significativo
        # e non dipende dalla precisione esatta del float.
        appena_sopra_70 = int(self.SOGLIA * 0.701 * 1024 * 1024)
        assert classify_memory_tier(appena_sopra_70, self.SOGLIA) == MemoryTier.WARNING

    def test_appena_sotto_100_percento_e_ancora_warning(self):
        appena_sotto_soglia = int(self.SOGLIA * 0.99 * 1024 * 1024)
        assert classify_memory_tier(appena_sotto_soglia, self.SOGLIA) == MemoryTier.WARNING

    def test_esattamente_alla_soglia_e_critical(self):
        alla_soglia = self.SOGLIA * 1024 * 1024
        assert classify_memory_tier(alla_soglia, self.SOGLIA) == MemoryTier.CRITICAL

    def test_appena_sotto_130_percento_e_ancora_critical(self):
        appena_sotto_emergency = int(self.SOGLIA * 1.29 * 1024 * 1024)
        assert classify_memory_tier(appena_sotto_emergency, self.SOGLIA) == MemoryTier.CRITICAL

    def test_al_130_percento_e_emergency(self):
        appena_sopra_130 = int(self.SOGLIA * 1.301 * 1024 * 1024)
        assert classify_memory_tier(appena_sopra_130, self.SOGLIA) == MemoryTier.EMERGENCY

    def test_molto_oltre_e_emergency(self):
        assert classify_memory_tier(5000 * 1024 * 1024, self.SOGLIA) == MemoryTier.EMERGENCY


class TestShouldForceGc:
    def test_normal_non_forza_gc(self):
        assert should_force_gc(100 * 1024 * 1024, critical_threshold_mb=512) is False

    def test_warning_forza_gc(self):
        # Diversamente da prima (solo a CRITICAL): da WARNING in su,
        # intervenire prima che il problema sia già serio.
        appena_sopra_70 = int(512 * 0.701 * 1024 * 1024)
        assert should_force_gc(appena_sopra_70, critical_threshold_mb=512) is True

    def test_critical_forza_gc(self):
        assert should_force_gc(600 * 1024 * 1024, critical_threshold_mb=512) is True

    def test_emergency_forza_gc(self):
        assert should_force_gc(5000 * 1024 * 1024, critical_threshold_mb=512) is True


class TestShouldDisconnectVoiceClient:
    def test_canale_vuoto_va_disconnesso(self):
        assert should_disconnect_voice_client(member_count_excluding_bot=0) is True

    def test_canale_con_persone_non_va_disconnesso(self):
        assert should_disconnect_voice_client(member_count_excluding_bot=1) is False
        assert should_disconnect_voice_client(member_count_excluding_bot=5) is False
