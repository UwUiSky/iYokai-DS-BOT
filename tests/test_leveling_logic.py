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
    MINIMUM_BALANCE_AFTER_DECAY,
    WEEKLY_PERSONAL_DECAY_RATE,
    apply_weekly_personal_decay,
    can_claim_daily,
    can_claim_work,
    can_earn_text_xp,
    compute_voice_minute,
    did_level_up,
    is_eligible_for_voice_xp,
    level_for_xp,
    period_key,
    seconds_until_next_claim,
    week_key,
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


class TestDailyWorkCooldown:
    def test_mai_reclamato_puo_reclamare_daily(self):
        assert can_claim_daily(last_daily_at=None) is True

    def test_reclamato_da_poco_non_puo_reclamare_daily(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(hours=1)
        assert can_claim_daily(last_daily_at=ultimo, now=ora) is False

    def test_reclamato_da_24_ore_puo_reclamare_daily(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(hours=24)
        assert can_claim_daily(last_daily_at=ultimo, now=ora) is True

    def test_mai_reclamato_puo_reclamare_work(self):
        assert can_claim_work(last_work_at=None) is True

    def test_reclamato_da_poco_non_puo_reclamare_work(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(minutes=30)
        assert can_claim_work(last_work_at=ultimo, now=ora) is False

    def test_reclamato_da_unora_puo_reclamare_work(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(hours=1)
        assert can_claim_work(last_work_at=ultimo, now=ora) is True


class TestSecondsUntilNextClaim:
    def test_mai_reclamato_zero_secondi_di_attesa(self):
        assert seconds_until_next_claim(None, cooldown_seconds=3600) == 0

    def test_cooldown_gia_scaduto_zero_secondi_di_attesa(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(hours=2)
        assert seconds_until_next_claim(ultimo, cooldown_seconds=3600, now=ora) == 0

    def test_a_meta_del_cooldown_restano_meta_dei_secondi(self):
        ora = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ultimo = ora - timedelta(seconds=1800)
        rimanenti = seconds_until_next_claim(ultimo, cooldown_seconds=3600, now=ora)
        assert rimanenti == 1800


class TestWeekKey:
    def test_formato_chiave_settimana_iso(self):
        # 2026-01-01 è un giovedì della settimana ISO 2026-W01
        momento = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert week_key(momento) == "2026-W01"

    def test_settimane_diverse_danno_chiavi_diverse(self):
        settimana_1 = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
        settimana_2 = datetime(2026, 1, 12, 0, 0, 0, tzinfo=timezone.utc)
        assert week_key(settimana_1) != week_key(settimana_2)

    def test_stessa_settimana_iso_stessa_chiave_anche_a_cavallo_di_mese(self):
        # 2025-12-29 (lunedì) e 2026-01-02 (venerdì) sono nella stessa
        # settimana ISO, anche se in mesi/anni civili diversi.
        lunedi = datetime(2025, 12, 29, 0, 0, 0, tzinfo=timezone.utc)
        venerdi = datetime(2026, 1, 2, 23, 0, 0, tzinfo=timezone.utc)
        assert week_key(lunedi) == week_key(venerdi)

    def test_senza_argomento_usa_now_utc(self):
        # Non deve lanciare eccezioni e deve restituire un formato valido.
        chiave = week_key()
        assert len(chiave) == 8
        assert chiave[5] == "W"


class TestApplyWeeklyPersonalDecay:
    def test_decadimento_normale_arrotonda_a_intero(self):
        # 10% di 100 = 10 esatto, nessun arrotondamento necessario
        assert apply_weekly_personal_decay(100) == 90

    def test_decadimento_arrotonda_per_difetto_su_percentuale_pari(self):
        # 10% di 105 = 10.5 -> round() python arrotonda a 10 (banker's
        # rounding su .5), risultato intero comunque, non 10.5
        risultato = apply_weekly_personal_decay(105)
        assert risultato == round(105 - round(105 * WEEKLY_PERSONAL_DECAY_RATE))
        assert isinstance(risultato, int)
        assert risultato in (94, 95)

    def test_decadimento_mai_negativo_e_mai_sotto_il_minimo(self):
        assert apply_weekly_personal_decay(1) == 1
        assert apply_weekly_personal_decay(0) == 0

    def test_saldo_piccolo_non_scende_sotto_il_minimo(self):
        for saldo in range(0, 15):
            risultato = apply_weekly_personal_decay(saldo)
            assert risultato >= min(saldo, MINIMUM_BALANCE_AFTER_DECAY)
            assert risultato <= saldo

    def test_risultato_e_sempre_intero(self):
        for saldo in (2, 3, 7, 11, 13, 17, 23, 999, 1000, 123456):
            risultato = apply_weekly_personal_decay(saldo)
            assert isinstance(risultato, int)
            assert risultato == int(risultato)

    def test_decadimento_non_supera_mai_il_saldo_originale(self):
        for saldo in (1, 2, 10, 100, 1000, 1_000_000):
            assert apply_weekly_personal_decay(saldo) <= saldo

    def test_decadimento_su_saldo_grande(self):
        # 10% di 1_000_000 = 100_000 esatto
        assert apply_weekly_personal_decay(1_000_000) == 900_000
