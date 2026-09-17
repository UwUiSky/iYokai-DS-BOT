"""
tests/test_welcome_logic.py
==============================
Test di core/welcome_logic.py — logica pura, tutte le combinazioni
delle due condizioni in ingresso (4 casi totali, esaustivi).
"""

from core.welcome_logic import choose_welcome_target


class TestChooseWelcomeTarget:
    def test_system_channel_disponibile_ha_priorita(self):
        target = choose_welcome_target(
            can_send_in_system_channel=True, has_any_writable_channel=True
        )
        assert target == "system_channel"

    def test_system_channel_disponibile_anche_senza_altri_canali(self):
        target = choose_welcome_target(
            can_send_in_system_channel=True, has_any_writable_channel=False
        )
        assert target == "system_channel"

    def test_senza_system_channel_usa_primo_canale_scrivibile(self):
        target = choose_welcome_target(
            can_send_in_system_channel=False, has_any_writable_channel=True
        )
        assert target == "first_writable_channel"

    def test_nessun_canale_disponibile_ricade_su_dm_owner(self):
        target = choose_welcome_target(
            can_send_in_system_channel=False, has_any_writable_channel=False
        )
        assert target == "dm_owner"
