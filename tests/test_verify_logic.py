"""
tests/test_verify_logic.py
=============================
Test di core/verify_logic.py — logica pura, nessuna dipendenza da
Discord. L'ordine di priorità blacklist > whitelist > controlli è il
punto più delicato, coperto esplicitamente.
"""

from datetime import datetime, timedelta, timezone

from core.verify_logic import (
    decide_verify_outcome,
    meets_account_age,
    meets_mutual_servers,
)


class TestMeetsAccountAge:
    def test_controllo_disattivato_passa_sempre(self):
        ora = datetime(2026, 1, 1, tzinfo=timezone.utc)
        account_appena_creato = ora
        assert meets_account_age(account_appena_creato, min_age_days=0, now=ora) is True

    def test_account_troppo_giovane_non_passa(self):
        ora = datetime(2026, 1, 10, tzinfo=timezone.utc)
        creato = ora - timedelta(days=2)
        assert meets_account_age(creato, min_age_days=7, now=ora) is False

    def test_account_abbastanza_vecchio_passa(self):
        ora = datetime(2026, 1, 10, tzinfo=timezone.utc)
        creato = ora - timedelta(days=10)
        assert meets_account_age(creato, min_age_days=7, now=ora) is True

    def test_esattamente_al_confine_passa(self):
        ora = datetime(2026, 1, 10, tzinfo=timezone.utc)
        creato = ora - timedelta(days=7)
        assert meets_account_age(creato, min_age_days=7, now=ora) is True


class TestMeetsMutualServers:
    def test_controllo_disattivato_passa_sempre(self):
        assert meets_mutual_servers(mutual_count=0, min_required=0) is True

    def test_sotto_soglia_non_passa(self):
        assert meets_mutual_servers(mutual_count=1, min_required=3) is False

    def test_sopra_soglia_passa(self):
        assert meets_mutual_servers(mutual_count=5, min_required=3) is True

    def test_esattamente_alla_soglia_passa(self):
        assert meets_mutual_servers(mutual_count=3, min_required=3) is True


class TestDecideVerifyOutcome:
    def test_tutti_i_controlli_passati_e_successo(self):
        esito = decide_verify_outcome(
            is_whitelisted=False, is_blacklisted=False,
            age_ok=True, mutual_ok=True, captcha_ok=True,
        )
        assert esito.success is True

    def test_blacklist_vince_su_tutto_anche_se_whitelisted(self):
        # Il caso più importante: un utente blacklistato NON deve
        # poter passare nemmeno se per errore è anche in whitelist.
        esito = decide_verify_outcome(
            is_whitelisted=True, is_blacklisted=True,
            age_ok=True, mutual_ok=True, captcha_ok=True,
        )
        assert esito.success is False
        assert "blacklisted" in esito.reason.lower()

    def test_whitelist_bypassa_controlli_falliti(self):
        esito = decide_verify_outcome(
            is_whitelisted=True, is_blacklisted=False,
            age_ok=False, mutual_ok=False, captcha_ok=False,
        )
        assert esito.success is True

    def test_eta_account_insufficiente_blocca(self):
        esito = decide_verify_outcome(
            is_whitelisted=False, is_blacklisted=False,
            age_ok=False, mutual_ok=True, captcha_ok=True,
        )
        assert esito.success is False
        assert "age" in esito.reason.lower()

    def test_mutual_servers_insufficienti_blocca(self):
        esito = decide_verify_outcome(
            is_whitelisted=False, is_blacklisted=False,
            age_ok=True, mutual_ok=False, captcha_ok=True,
        )
        assert esito.success is False
        assert "mutual" in esito.reason.lower()

    def test_captcha_fallito_blocca(self):
        esito = decide_verify_outcome(
            is_whitelisted=False, is_blacklisted=False,
            age_ok=True, mutual_ok=True, captcha_ok=False,
        )
        assert esito.success is False
        assert "captcha" in esito.reason.lower()

    def test_reason_sempre_valorizzato_anche_nel_successo(self):
        esito = decide_verify_outcome(
            is_whitelisted=False, is_blacklisted=False,
            age_ok=True, mutual_ok=True, captcha_ok=True,
        )
        assert esito.reason != ""
