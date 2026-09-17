"""
tests/test_leveling_logic.py
===============================
Test di core/leveling_logic.py — logica pura, nessuna dipendenza da
Discord o dal database.
"""

from datetime import datetime, timedelta, timezone

from core.leveling_logic import (
    DAILY_CAP_MINUTES,
    MAX_CONSECUTIVE_MINUTES_SAME_CHANNEL,
    can_earn_text_xp,
    compute_voice_minute,
    did_level_up,
    is_eligible_for_voice_xp,
    level_for_xp,
    period_key,
    xp_for_level,
)


class TestPeriodKey:
    def test_formato_anno_mese(self):
        momento = datetime(2026, 9, 17, tzinfo=timezone.utc)
        assert period_key(momento) == "2026-09"

    def test_mese_a_una_cifra_ha_lo_zero_iniziale(self):
        momento = datetime(2026, 3, 5, tzinfo=timezone.utc)
        assert period_key(momento) == "2026-03"

    def test_mesi_diversi_producono_chiavi_diverse(self):
        settembre = datetime(2026, 9, 30, tzinfo=timezone.utc)
        ottobre = datetime(2026, 10, 1, tzinfo=timezone.utc)
        assert period_key(settembre) != period_key(ottobre)


class TestCanEarnTextXp:
    def test_primo_messaggio_di_sempre_guadagna_sempre(self):
        assert can_earn_text_xp(last_xp_at=None) is True

    def test_messaggio_subito_dopo_non_guadagna(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=5)
        assert can_earn_text_xp(last_xp_at=ultimo, now=ora) is False

    def test_messaggio_dopo_il_cooldown_guadagna(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=61)
        assert can_earn_text_xp(last_xp_at=ultimo, now=ora) is True

    def test_esattamente_al_confine_del_cooldown_guadagna(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=60)
        assert can_earn_text_xp(last_xp_at=ultimo, now=ora) is True


class TestIsEligibleForVoiceXp:
    def test_condizioni_tutte_soddisfatte(self):
        assert is_eligible_for_voice_xp(
            is_self_deaf=False, is_afk_channel=False, other_members_not_self_muted=1
        ) is True

    def test_self_deaf_blocca(self):
        assert is_eligible_for_voice_xp(
            is_self_deaf=True, is_afk_channel=False, other_members_not_self_muted=1
        ) is False

    def test_canale_afk_blocca(self):
        assert is_eligible_for_voice_xp(
            is_self_deaf=False, is_afk_channel=True, other_members_not_self_muted=1
        ) is False

    def test_nessun_altro_non_mutato_blocca(self):
        # Da solo, o con altri ma tutti self_mute: non conta come
        # attività reale.
        assert is_eligible_for_voice_xp(
            is_self_deaf=False, is_afk_channel=False, other_members_not_self_muted=0
        ) is False

    def test_piu_persone_non_mutate_va_bene(self):
        assert is_eligible_for_voice_xp(
            is_self_deaf=False, is_afk_channel=False, other_members_not_self_muted=5
        ) is True


class TestComputeVoiceMinute:
    def test_primo_minuto_nel_canale(self):
        risultato = compute_voice_minute(
            consecutive_minutes_in_channel=0, minutes_today=0, changed_channel=False
        )
        assert risultato.xp_granted > 0
        assert risultato.coins_granted > 0
        assert risultato.new_consecutive_minutes == 1
        assert risultato.new_minutes_today == 1
        assert risultato.capped is False

    def test_cambio_canale_riparte_il_contatore_da_uno(self):
        risultato = compute_voice_minute(
            consecutive_minutes_in_channel=90, minutes_today=90, changed_channel=True
        )
        # Il contatore di minuti CONSECUTIVI NELLO STESSO CANALE
        # riparte da 1 (questo minuto conta), ma i minuti totali di
        # oggi continuano a salire normalmente.
        assert risultato.new_consecutive_minutes == 1
        assert risultato.new_minutes_today == 91
        assert risultato.xp_granted > 0  # è tornato idoneo, riparte da zero

    def test_esattamente_al_limite_delle_2_ore_guadagna_ancora(self):
        # Al minuto 119 -> 120esimo minuto: è ancora entro il limite
        # (120 non è "oltre" 120).
        risultato = compute_voice_minute(
            consecutive_minutes_in_channel=MAX_CONSECUTIVE_MINUTES_SAME_CHANNEL - 1,
            minutes_today=0,
            changed_channel=False,
        )
        assert risultato.new_consecutive_minutes == MAX_CONSECUTIVE_MINUTES_SAME_CHANNEL
        assert risultato.xp_granted > 0

    def test_oltre_le_2_ore_consecutive_non_guadagna(self):
        risultato = compute_voice_minute(
            consecutive_minutes_in_channel=MAX_CONSECUTIVE_MINUTES_SAME_CHANNEL,
            minutes_today=0,
            changed_channel=False,
        )
        assert risultato.new_consecutive_minutes == MAX_CONSECUTIVE_MINUTES_SAME_CHANNEL + 1
        assert risultato.xp_granted == 0
        assert risultato.coins_granted == 0

    def test_il_contatore_continua_a_salire_anche_oltre_il_limite(self):
        # Non si blocca sul valore limite: continua a contare, per
        # coerenza se il limite venisse cambiato in futuro (vedi
        # docstring della funzione).
        risultato = compute_voice_minute(
            consecutive_minutes_in_channel=200, minutes_today=0, changed_channel=False
        )
        assert risultato.new_consecutive_minutes == 201

    def test_cap_giornaliero_raggiunto_non_guadagna(self):
        risultato = compute_voice_minute(
            consecutive_minutes_in_channel=0,
            minutes_today=DAILY_CAP_MINUTES,
            changed_channel=False,
        )
        assert risultato.xp_granted == 0
        assert risultato.coins_granted == 0
        assert risultato.capped is True

    def test_appena_sotto_il_cap_giornaliero_guadagna_ancora(self):
        risultato = compute_voice_minute(
            consecutive_minutes_in_channel=0,
            minutes_today=DAILY_CAP_MINUTES - 1,
            changed_channel=False,
        )
        assert risultato.xp_granted > 0
        assert risultato.capped is False

    def test_limite_2_ore_ha_priorita_sul_cap_giornaliero_nel_flag_capped(self):
        # Se scatta il limite delle 2 ore, il flag "capped" (che
        # indica specificamente il CAP GIORNALIERO) resta False:
        # sono due limiti distinti, il chiamante potrebbe voler
        # comunicare messaggi diversi in futuro.
        risultato = compute_voice_minute(
            consecutive_minutes_in_channel=MAX_CONSECUTIVE_MINUTES_SAME_CHANNEL,
            minutes_today=0,
            changed_channel=False,
        )
        assert risultato.capped is False


class TestXpForLevel:
    def test_livello_zero_richiede_zero_xp(self):
        assert xp_for_level(0) == 0

    def test_livello_negativo_richiede_zero_xp(self):
        assert xp_for_level(-5) == 0

    def test_xp_cresce_con_il_livello(self):
        assert xp_for_level(1) < xp_for_level(2) < xp_for_level(3)


class TestLevelForXp:
    def test_zero_xp_e_livello_zero(self):
        assert level_for_xp(0) == 0

    def test_xp_esatto_della_soglia_raggiunge_quel_livello(self):
        soglia_livello_5 = xp_for_level(5)
        assert level_for_xp(soglia_livello_5) == 5

    def test_un_xp_in_meno_della_soglia_non_raggiunge_il_livello(self):
        soglia_livello_5 = xp_for_level(5)
        assert level_for_xp(soglia_livello_5 - 1) == 4

    def test_xp_altissimo_produce_livello_alto_coerente(self):
        xp_alto = xp_for_level(50) + 10
        livello = level_for_xp(xp_alto)
        assert livello == 50
        # Verifica di coerenza incrociata: la soglia del livello
        # trovato deve essere <= xp, e quella del livello successivo
        # deve essere > xp.
        assert xp_for_level(livello) <= xp_alto
        assert xp_for_level(livello + 1) > xp_alto


class TestDidLevelUp:
    def test_guadagno_che_non_fa_salire_livello(self):
        soglia_3 = xp_for_level(3)
        salito, nuovo_livello = did_level_up(xp_before=soglia_3, xp_after=soglia_3 + 1)
        assert salito is False
        assert nuovo_livello == 3

    def test_guadagno_che_fa_salire_di_un_livello(self):
        soglia_3 = xp_for_level(3)
        salito, nuovo_livello = did_level_up(xp_before=soglia_3 - 1, xp_after=soglia_3)
        assert salito is True
        assert nuovo_livello == 3

    def test_guadagno_enorme_che_fa_saltare_piu_livelli(self):
        salito, nuovo_livello = did_level_up(xp_before=0, xp_after=xp_for_level(10))
        assert salito is True
        assert nuovo_livello == 10
