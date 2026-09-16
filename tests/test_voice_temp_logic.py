"""
tests/test_voice_temp_logic.py
=================================
Test di core/voice_temp_logic.py — logica pura, nessuna dipendenza
da Discord.
"""

from core.voice_temp_logic import (
    can_manage_voice_channel,
    is_generator_join,
    should_delete_after_leave,
)


class TestIsGeneratorJoin:
    def test_ingresso_nel_generatore(self):
        assert is_generator_join(after_channel_id=42, generator_channel_id=42) is True

    def test_ingresso_in_altro_canale(self):
        assert is_generator_join(after_channel_id=99, generator_channel_id=42) is False

    def test_nessun_generatore_configurato(self):
        assert is_generator_join(after_channel_id=42, generator_channel_id=None) is False

    def test_utente_non_e_entrato_in_nessun_vocale(self):
        # after_channel_id None: l'utente si è disconnesso, non ha
        # raggiunto nessun canale.
        assert is_generator_join(after_channel_id=None, generator_channel_id=42) is False


class TestShouldDeleteAfterLeave:
    def test_canale_tracciato_e_vuoto_va_eliminato(self):
        assert should_delete_after_leave(
            left_channel_id=42, is_tracked_temp_channel=True, remaining_member_count=0
        ) is True

    def test_canale_tracciato_ma_non_vuoto_non_va_eliminato(self):
        assert should_delete_after_leave(
            left_channel_id=42, is_tracked_temp_channel=True, remaining_member_count=1
        ) is False

    def test_canale_non_tracciato_non_va_mai_eliminato(self):
        # Anche se vuoto: non è un canale temporaneo creato da questo
        # modulo, non è compito suo eliminarlo.
        assert should_delete_after_leave(
            left_channel_id=42, is_tracked_temp_channel=False, remaining_member_count=0
        ) is False

    def test_nessun_canale_lasciato(self):
        assert should_delete_after_leave(
            left_channel_id=None, is_tracked_temp_channel=True, remaining_member_count=0
        ) is False


class TestCanManageVoiceChannel:
    def test_proprietario_puo_gestire(self):
        assert can_manage_voice_channel(
            actor_id=1, owner_id=1, actor_has_manage_channels=False
        ) is True

    def test_staff_con_manage_channels_puo_gestire_canale_altrui(self):
        assert can_manage_voice_channel(
            actor_id=2, owner_id=1, actor_has_manage_channels=True
        ) is True

    def test_utente_qualunque_non_puo_gestire_canale_altrui(self):
        assert can_manage_voice_channel(
            actor_id=2, owner_id=1, actor_has_manage_channels=False
        ) is False
