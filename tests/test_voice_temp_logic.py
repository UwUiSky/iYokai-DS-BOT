"""
tests/test_voice_temp_logic.py
=================================
Test di core/voice_temp_logic.py — logica pura, nessuna dipendenza
da Discord.
"""

import pytest

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


# #127 VOC-011/012: nome dei canali da un modello con {utente} e {numero}
from core.voice_temp_logic import errore_modello_nome, nome_da_modello, primo_numero_libero


class TestModelloNome:
    def test_senza_modello_resta_il_nome_di_sempre(self):
        assert nome_da_modello(None, "Ada", 3) == "Canale di Ada"

    def test_modello_con_utente_e_numero(self):
        assert nome_da_modello("Stanza {numero} · {utente}", "Ada", 2) == "Stanza 2 · Ada"

    def test_nome_lungo_tagliato_a_100(self):
        assert len(nome_da_modello("{utente}", "x" * 300, 1)) == 100

    def test_segnaposto_sconosciuto_e_un_errore(self):
        assert errore_modello_nome("Stanza {nome}") is not None

    def test_graffa_rotta_e_un_errore(self):
        assert errore_modello_nome("Stanza {numero") is not None

    def test_modello_valido(self):
        assert errore_modello_nome("Stanza {numero}") is None

    def test_primo_numero_libero_riempie_i_buchi(self):
        assert primo_numero_libero([]) == 1
        assert primo_numero_libero([1, 2, 4]) == 3
        assert primo_numero_libero([2, 3]) == 1


# Cacciatore-bug r7liv: il modello non deve poter usare specifiche di formato.
@pytest.mark.parametrize("modello", ["Stanza {numero:>500}", "{utente!r}", "{numero:{utente}}", "{numero:d}x"])
def test_modello_con_specifiche_di_formato_rifiutato(modello):
    from core.voice_temp_logic import errore_modello_nome

    assert errore_modello_nome(modello) is not None


def test_nome_da_modello_non_usa_il_nome_utente_come_formato():
    from core.voice_temp_logic import nome_da_modello

    # Un modello già salvato non può far esplodere la creazione del canale.
    assert nome_da_modello("{numero:{utente}}", "999999999", 3) == "3"
    assert nome_da_modello("Stanza {numero} di {utente}", "{numero}", 2) == "Stanza 2 di {numero}"
    assert nome_da_modello("{{x}} {numero}", "u", 1) == "{x} 1"
