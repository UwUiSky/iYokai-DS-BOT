"""
tests/test_guild_clan_logic.py
==================================
Test di core/guild_clan_logic.py — logica pura.
"""

import pytest

from core.guild_clan_logic import (
    CHANNEL_UNLOCK_COSTS,
    CREATION_DEFICIT,
    apply_monthly_treasury_decay,
    compute_tick_decay_factor,
    compute_tick_reward,
    is_creation_deficit_covered,
    next_channel_unlock_cost,
    validate_guild_tag,
)


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
        assert xp == 30
        assert coin == 2

    def test_tetto_giornaliero_raggiunto_zero(self):
        xp, coin = compute_tick_reward(ticks_in_same_channel=0, ticks_today=720)
        assert (xp, coin) == (0, 0)

    def test_decadimento_a_meta_dimezza_il_guadagno(self):
        xp, coin = compute_tick_reward(ticks_in_same_channel=90, ticks_today=0)
        assert xp == 15  # 30 * 0.5
        assert coin == 1  # 2 * 0.5

    def test_utente_molto_attivo_un_mese_intero_rientra_nel_range_concordato(self):
        """
        Verifica diretta del numero concordato con l'utente: un
        utente che fa 12h/giorno tutti i giorni per un mese, SENZA
        mai subire decadimento (cambia vocale abbastanza spesso),
        deve arrivare a circa 500-750k XP e restare sotto i 50k coin.
        """
        xp_totale = coin_totale = 0
        for _ in range(720):  # 720 tick/giorno x 30 giorni, nessun decadimento
            xp, coin = compute_tick_reward(ticks_in_same_channel=0, ticks_today=0)
            xp_totale += xp
            coin_totale += coin
        xp_mensile = xp_totale * 30
        coin_mensile = coin_totale * 30

        assert 500_000 <= xp_mensile <= 750_000
        assert coin_mensile < 50_000


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


class TestIsCreationDeficitCovered:
    def test_deficit_iniziale_non_coperto(self):
        assert is_creation_deficit_covered(-CREATION_DEFICIT) is False

    def test_saldo_esattamente_zero_coperto(self):
        assert is_creation_deficit_covered(0) is True

    def test_saldo_positivo_coperto(self):
        assert is_creation_deficit_covered(500) is True

    def test_ancora_in_deficit_parziale_non_coperto(self):
        assert is_creation_deficit_covered(-1) is False
