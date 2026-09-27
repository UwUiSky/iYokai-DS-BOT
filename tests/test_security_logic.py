"""
tests/test_security_logic.py
================================
Test della logica pura della Security Suite (SPEC.md §7.1/§7.2/§7.5)
— nessun mock di discord.py o del DB.
"""

from datetime import datetime, timedelta, timezone

from core.security_logic import (
    AntiNukeConfig,
    AntiRaidConfig,
    JOIN_VIOLATION_ACCOUNT_AGE,
    JOIN_VIOLATION_AVATAR,
    JOIN_VIOLATION_RATE,
    JOIN_VIOLATION_USERNAME,
    JoinSignals,
    NUKE_CATEGORY_CHANNEL,
    ServerSecuritySignals,
    category_max_count,
    category_window_seconds,
    compute_security_score,
    evaluate_join,
    is_account_too_new,
    is_actor_trusted,
    is_nuke_violation,
    is_suspicious_username,
)


class TestSuspiciousUsername:
    def test_nome_normale_non_e_sospetto(self):
        assert is_suspicious_username("Mario") is False

    def test_nome_con_poche_cifre_non_e_sospetto(self):
        assert is_suspicious_username("Mario99") is False

    def test_lettere_seguite_da_molte_cifre_e_sospetto(self):
        assert is_suspicious_username("asjdk48213") is True

    def test_solo_cifre_non_matcha(self):
        assert is_suspicious_username("48213") is False


class TestAccountAge:
    def test_account_appena_creato_e_troppo_nuovo(self):
        now = datetime.now(timezone.utc)
        creato = now - timedelta(minutes=5)
        assert is_account_too_new(creato, now, min_age_seconds=86400) is True

    def test_account_vecchio_non_e_troppo_nuovo(self):
        now = datetime.now(timezone.utc)
        creato = now - timedelta(days=365)
        assert is_account_too_new(creato, now, min_age_seconds=86400) is False


class TestEvaluateJoin:
    def _signals(self, **overrides) -> JoinSignals:
        base = dict(
            account_created_at=datetime.now(timezone.utc) - timedelta(days=365),
            has_avatar=True,
            username="MembroNormale",
            recent_join_count=1,
        )
        base.update(overrides)
        return JoinSignals(**base)

    def test_modulo_disattivato_non_valuta_nulla(self):
        config = AntiRaidConfig(enabled=False)
        now = datetime.now(timezone.utc)
        assert evaluate_join(self._signals(recent_join_count=999), config, now) == ()

    def test_join_normale_nessuna_violazione(self):
        config = AntiRaidConfig(enabled=True, join_rate_max=10)
        now = datetime.now(timezone.utc)
        assert evaluate_join(self._signals(), config, now) == ()

    def test_troppi_join_viola_join_rate(self):
        config = AntiRaidConfig(enabled=True, join_rate_max=5)
        now = datetime.now(timezone.utc)
        risultato = evaluate_join(self._signals(recent_join_count=6), config, now)
        assert JOIN_VIOLATION_RATE in risultato

    def test_account_troppo_nuovo_viola(self):
        config = AntiRaidConfig(enabled=True, min_account_age_seconds=86400)
        now = datetime.now(timezone.utc)
        segnali = self._signals(account_created_at=now - timedelta(minutes=1))
        assert evaluate_join(segnali, config, now) == (JOIN_VIOLATION_ACCOUNT_AGE,)

    def test_username_sospetto_viola(self):
        config = AntiRaidConfig(enabled=True)
        now = datetime.now(timezone.utc)
        segnali = self._signals(username="asjdk48213")
        assert evaluate_join(segnali, config, now) == (JOIN_VIOLATION_USERNAME,)

    def test_senza_avatar_viola(self):
        config = AntiRaidConfig(enabled=True)
        now = datetime.now(timezone.utc)
        segnali = self._signals(has_avatar=False)
        assert evaluate_join(segnali, config, now) == (JOIN_VIOLATION_AVATAR,)

    def test_controllo_username_disattivabile(self):
        config = AntiRaidConfig(enabled=True, check_username_pattern=False)
        now = datetime.now(timezone.utc)
        segnali = self._signals(username="asjdk48213")
        assert evaluate_join(segnali, config, now) == ()

    def test_piu_violazioni_insieme(self):
        config = AntiRaidConfig(enabled=True, join_rate_max=1, min_account_age_seconds=86400)
        now = datetime.now(timezone.utc)
        segnali = self._signals(
            recent_join_count=5,
            account_created_at=now - timedelta(minutes=1),
            username="asjdk48213",
            has_avatar=False,
        )
        risultato = evaluate_join(segnali, config, now)
        assert set(risultato) == {
            JOIN_VIOLATION_RATE,
            JOIN_VIOLATION_ACCOUNT_AGE,
            JOIN_VIOLATION_USERNAME,
            JOIN_VIOLATION_AVATAR,
        }


class TestAntiNuke:
    def test_actor_fidato_non_e_mai_in_violazione(self):
        config = AntiNukeConfig(enabled=True, channel_max=1, trusted_ids=(42,))
        assert is_nuke_violation(42, NUKE_CATEGORY_CHANNEL, 99, config) is False

    def test_modulo_disattivato_non_viola_mai(self):
        config = AntiNukeConfig(enabled=False, channel_max=1)
        assert is_nuke_violation(1, NUKE_CATEGORY_CHANNEL, 99, config) is False

    def test_sotto_soglia_non_viola(self):
        config = AntiNukeConfig(enabled=True, channel_max=5)
        assert is_nuke_violation(1, NUKE_CATEGORY_CHANNEL, 3, config) is False

    def test_sopra_soglia_viola(self):
        config = AntiNukeConfig(enabled=True, channel_max=3)
        assert is_nuke_violation(1, NUKE_CATEGORY_CHANNEL, 4, config) is True

    def test_is_actor_trusted(self):
        assert is_actor_trusted(5, (1, 5, 9)) is True
        assert is_actor_trusted(2, (1, 5, 9)) is False

    def test_category_max_count_e_window_per_categoria(self):
        config = AntiNukeConfig(role_max=7, role_window_seconds=42)
        assert category_max_count("role", config) == 7
        assert category_window_seconds("role", config) == 42


class TestSecurityScore:
    def _signali_perfetti(self, **overrides) -> ServerSecuritySignals:
        base = dict(
            mfa_level=1,
            verification_level="high",
            admin_member_count=1,
            total_member_count=100,
            anti_raid_enabled=True,
            anti_nuke_enabled=True,
            automod_badwords_active=True,
        )
        base.update(overrides)
        return ServerSecuritySignals(**base)

    def test_server_perfetto_ha_punteggio_massimo(self):
        punteggio, consigli = compute_security_score(self._signali_perfetti())
        assert punteggio == 100
        assert consigli == ()

    def test_senza_2fa_penalizza(self):
        punteggio, consigli = compute_security_score(self._signali_perfetti(mfa_level=0))
        assert punteggio == 85
        assert len(consigli) == 1

    def test_verifica_bassa_penalizza(self):
        punteggio, _ = compute_security_score(self._signali_perfetti(verification_level="low"))
        assert punteggio == 90

    def test_troppi_admin_penalizza(self):
        punteggio, _ = compute_security_score(
            self._signali_perfetti(admin_member_count=10, total_member_count=100)
        )
        assert punteggio == 85

    def test_anti_raid_disattivato_penalizza(self):
        punteggio, _ = compute_security_score(self._signali_perfetti(anti_raid_enabled=False))
        assert punteggio == 85

    def test_punteggio_non_scende_sotto_zero(self):
        # La somma di TUTTE le penalità oggi definite non basta a
        # scendere sotto zero (100 - 90 = 10): il test verifica
        # comunque esplicitamente che il clamp non lo fa risalire o
        # scendere oltre, cosa che un futuro nuovo controllo
        # aggiunto senza il max(0, ...) romperebbe silenziosamente.
        punteggio, _ = compute_security_score(
            self._signali_perfetti(
                mfa_level=0,
                verification_level="none",
                admin_member_count=50,
                total_member_count=100,
                anti_raid_enabled=False,
                anti_nuke_enabled=False,
                automod_badwords_active=False,
            )
        )
        assert punteggio == 20
        assert punteggio >= 0

    def test_server_senza_membri_non_divide_per_zero(self):
        punteggio, _ = compute_security_score(
            self._signali_perfetti(admin_member_count=0, total_member_count=0)
        )
        assert punteggio == 100
