"""
tests/test_guild_clan_logic.py
==================================
Test di core/guild_clan_logic.py — logica pura.
"""

import pytest

from core.guild_clan_logic import (
    CHANNEL_UNLOCK_COSTS,
    CREATION_DEFICIT,
    TICK_COINS,
    TICK_XP,
    VOICE_HOURS_REQUIRED,
    apply_monthly_treasury_decay,
    compute_tick_decay_factor,
    compute_tick_reward,
    is_creation_deficit_covered,
    next_channel_unlock_cost,
    next_channel_voice_hours_requirement,
    validate_guild_tag,
    voice_ticks_to_hours,
)
from core.leveling_logic import VOICE_COINS_PER_MINUTE, VOICE_XP_PER_MINUTE


class TestValidateGuildTag:
    def test_tag_valido_lettere_ascii(self):
        valido, motivo = validate_guild_tag("ABC")
        assert valido is True
        assert motivo is None

    def test_tag_valido_un_carattere(self):
        assert validate_guild_tag("X")[0] is True

    def test_tag_valido_cinque_caratteri(self):
        assert validate_guild_tag("ABCDE")[0] is True

    def test_tag_troppo_lungo_rifiutato(self):
        valido, motivo = validate_guild_tag("ABCDEF")
        assert valido is False
        assert "caratteri" in motivo

    def test_tag_vuoto_rifiutato(self):
        assert validate_guild_tag("")[0] is False

    def test_tag_con_numeri_e_simboli(self):
        assert validate_guild_tag("A1!@")[0] is True

    def test_tag_giapponese_valido(self):
        assert validate_guild_tag("侍魂")[0] is True

    def test_tag_coreano_valido(self):
        assert validate_guild_tag("한국어")[0] is True

    def test_tag_cinque_caratteri_cjk_valido(self):
        # La lunghezza si misura in CARATTERI, non byte - 5 ideogrammi
        # devono passare esattamente come 5 lettere ASCII.
        assert validate_guild_tag("東京大阪市")[0] is True

    def test_tag_con_emoji_rifiutato(self):
        valido, motivo = validate_guild_tag("A😀B")
        assert valido is False
        assert "emoji" in motivo

    def test_tag_con_spazi_rifiutato(self):
        assert validate_guild_tag("A B")[0] is False


class TestComputeTickDecayFactor:
    def test_zero_tick_fattore_pieno(self):
        assert compute_tick_decay_factor(0) == 1.0

    def test_a_meta_decadimento(self):
        assert compute_tick_decay_factor(90) == 0.5  # metà di 180

    def test_al_limite_del_decadimento_fattore_zero(self):
        assert compute_tick_decay_factor(180) == 0.0

    def test_oltre_il_limite_resta_zero(self):
        assert compute_tick_decay_factor(500) == 0.0

    def test_tick_negativo_trattato_come_zero(self):
        assert compute_tick_decay_factor(-5) == 1.0


class TestComputeTickReward:
    def test_tasso_pieno_senza_decadimento_ne_tetto(self):
        xp, coin = compute_tick_reward(ticks_in_same_channel=0, ticks_today=0)
        assert xp == 10
        assert coin == 4

    def test_tetto_giornaliero_raggiunto_zero(self):
        xp, coin = compute_tick_reward(ticks_in_same_channel=0, ticks_today=720)
        assert (xp, coin) == (0, 0)

    def test_decadimento_a_meta_dimezza_il_guadagno(self):
        xp, coin = compute_tick_reward(ticks_in_same_channel=90, ticks_today=0)
        assert xp == 5  # 10 * 0.5
        assert coin == 2  # 4 * 0.5

    def test_tasso_di_gilda_e_esattamente_il_doppio_del_vocale_normale(self):
        """
        Verifica diretta della regola confermata dall'utente: il
        guadagno XP/coin nei canali vocali di gilda deve essere
        ESATTAMENTE ×2 rispetto al vocale normale (`core.leveling_
        logic.VOICE_XP_PER_MINUTE`/`VOICE_COINS_PER_MINUTE`), non un
        target assoluto calibrato a parte — entrambi i tick durano
        60 secondi, quindi i valori sono confrontabili 1:1 al minuto.
        Corregge una discrepanza reale trovata in una sessione
        precedente (era stato implementato un tasso 6× sull'XP e 1×
        sulle coin, con SPEC.md che dichiarava ×2).
        """
        assert TICK_XP == 2 * VOICE_XP_PER_MINUTE
        assert TICK_COINS == 2 * VOICE_COINS_PER_MINUTE


class TestApplyMonthlyTreasuryDecay:
    def test_decadimento_del_dieci_percento(self):
        assert apply_monthly_treasury_decay(100_000) == 90_000

    def test_saldo_zero_resta_zero(self):
        assert apply_monthly_treasury_decay(0) == 0

    def test_saldo_negativo_non_tocato(self):
        # Un saldo negativo (in fase di deficit di creazione) non è
        # "tesoreria inutilizzata" nel senso previsto qui - non ha
        # senso applicarci un decadimento percentuale.
        assert apply_monthly_treasury_decay(-5000) == -5000


class TestNextChannelUnlockCost:
    def test_primo_canale(self):
        assert next_channel_unlock_cost(0) == 25_000

    def test_secondo_canale(self):
        assert next_channel_unlock_cost(1) == 50_000

    def test_terzo_canale(self):
        assert next_channel_unlock_cost(2) == 200_000

    def test_quarto_canale(self):
        assert next_channel_unlock_cost(3) == 800_000

    def test_scala_esaurita_restituisce_none(self):
        assert next_channel_unlock_cost(4) is None

    def test_negativo_solleva(self):
        with pytest.raises(ValueError):
            next_channel_unlock_cost(-1)

    def test_costanti_coerenti_con_la_funzione(self):
        assert len(CHANNEL_UNLOCK_COSTS) == 4


class TestNextChannelVoiceHoursRequirement:
    def test_primo_canale(self):
        assert next_channel_voice_hours_requirement(0) == 12

    def test_secondo_canale(self):
        assert next_channel_voice_hours_requirement(1) == 24

    def test_terzo_canale(self):
        assert next_channel_voice_hours_requirement(2) == 96

    def test_quarto_canale(self):
        assert next_channel_voice_hours_requirement(3) == 384

    def test_scala_esaurita_restituisce_none(self):
        assert next_channel_voice_hours_requirement(4) is None

    def test_negativo_solleva(self):
        with pytest.raises(ValueError):
            next_channel_voice_hours_requirement(-1)

    def test_costanti_coerenti_con_la_funzione(self):
        assert len(VOICE_HOURS_REQUIRED) == len(CHANNEL_UNLOCK_COSTS)


class TestVoiceTicksToHours:
    def test_zero_tick_zero_ore(self):
        assert voice_ticks_to_hours(0) == 0

    def test_esattamente_unora(self):
        assert voice_ticks_to_hours(60) == 1

    def test_arrotonda_per_difetto(self):
        assert voice_ticks_to_hours(119) == 1

    def test_diverse_ore(self):
        assert voice_ticks_to_hours(720) == 12

    def test_negativo_solleva(self):
        with pytest.raises(ValueError):
            voice_ticks_to_hours(-1)


class TestIsCreationDeficitCovered:
    def test_deficit_iniziale_non_coperto(self):
        assert is_creation_deficit_covered(-CREATION_DEFICIT) is False

    def test_saldo_esattamente_zero_coperto(self):
        assert is_creation_deficit_covered(0) is True

    def test_saldo_positivo_coperto(self):
        assert is_creation_deficit_covered(500) is True

    def test_ancora_in_deficit_parziale_non_coperto(self):
        assert is_creation_deficit_covered(-1) is False
