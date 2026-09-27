"""
tests/test_voice_temp_logic.py
=================================
Test di core/voice_temp_logic.py — logica pura, nessuna dipendenza
da Discord.
"""

from core.voice_temp_logic import (
    can_manage_voice_channel,
    effective_category_cap,
    is_category_full,
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


class TestEffectiveCategoryCap:
    def test_nessun_cap_configurato_usa_il_limite_discord(self):
        assert effective_category_cap(None) == 50

    def test_cap_configurato_sotto_il_limite_discord(self):
        assert effective_category_cap(10) == 10

    def test_cap_configurato_sopra_il_limite_discord_viene_troncato(self):
        # Un admin non può mai superare il limite hard di Discord,
        # anche se lo imposta più alto per errore.
        assert effective_category_cap(999) == 50


class TestIsCategoryFull:
    def test_categoria_sotto_il_cap_non_e_piena(self):
        assert is_category_full(current_channel_count=5, configured_cap=10) is False

    def test_categoria_al_cap_e_piena(self):
        assert is_category_full(current_channel_count=10, configured_cap=10) is True

    def test_categoria_sopra_il_cap_e_piena(self):
        assert is_category_full(current_channel_count=11, configured_cap=10) is True

    def test_nessun_cap_configurato_usa_il_limite_discord_di_50(self):
        assert is_category_full(current_channel_count=49, configured_cap=None) is False
        assert is_category_full(current_channel_count=50, configured_cap=None) is True
