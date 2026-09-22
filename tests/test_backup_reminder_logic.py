"""
tests/test_backup_reminder_logic.py
=======================================
Test di core/backup_reminder_logic.py — logica pura.
"""

from datetime import datetime, timedelta, timezone

from core.backup_reminder_logic import (
    format_slot_wait_message,
    format_time_remaining,
    should_send_timeout_reminder,
)

ORA = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class TestShouldSendTimeoutReminder:
    def test_lontano_dalla_scadenza_non_manda_promemoria(self):
        creato = ORA
        adesso = ORA + timedelta(hours=5)  # 19h rimaste, ben oltre le 2h soglia
        assert should_send_timeout_reminder(creato, adesso, reminder_already_sent=False) is False

    def test_vicino_alla_scadenza_manda_promemoria(self):
        creato = ORA
        adesso = ORA + timedelta(hours=23)  # 1h rimasta, sotto le 2h soglia
        assert should_send_timeout_reminder(creato, adesso, reminder_already_sent=False) is True

    def test_esattamente_alla_soglia_manda_promemoria(self):
        creato = ORA
        adesso = ORA + timedelta(hours=22)  # esattamente 2h rimaste
        assert should_send_timeout_reminder(creato, adesso, reminder_already_sent=False) is True

    def test_gia_mandato_non_lo_manda_di_nuovo(self):
        creato = ORA
        adesso = ORA + timedelta(hours=23)
        assert should_send_timeout_reminder(creato, adesso, reminder_already_sent=True) is False

    def test_gia_scaduto_non_manda_un_promemoria_inutile(self):
        creato = ORA
        adesso = ORA + timedelta(hours=25)  # oltre le 24h, già scaduto
        assert should_send_timeout_reminder(creato, adesso, reminder_already_sent=False) is False


class TestFormatTimeRemaining:
    def test_formatta_ore_e_minuti(self):
        creato = ORA
        adesso = ORA + timedelta(hours=22, minutes=15)  # restano 1h 45m
        assert format_time_remaining(creato, adesso) == "1h 45m"

    def test_appena_creato_mostra_quasi_tutto_il_tempo(self):
        creato = ORA
        adesso = ORA
        assert format_time_remaining(creato, adesso) == "24h 0m"

    def test_scaduto_restituisce_testo_esplicito(self):
        creato = ORA
        adesso = ORA + timedelta(hours=25)
        assert format_time_remaining(creato, adesso) == "scaduto"


class TestFormatSlotWaitMessage:
    def test_include_il_conteggio_occupati_su_totali(self):
        messaggio = format_slot_wait_message(occupied_slots=10, max_slots=10)
        assert "10/10" in messaggio

    def test_include_il_limite_massimo_onesto_di_24_ore(self):
        messaggio = format_slot_wait_message(occupied_slots=10)
        assert "24 ore" in messaggio
