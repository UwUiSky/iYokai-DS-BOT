"""
tests/test_restore_batch_logic.py
=====================================
Test di plan_restore_action (SPEC.md §11.11) — logica pura.
"""

from core.repositories.restore_oauth_repo import (
    STATUS_ACTIVE,
    STATUS_BANNED_BLACKLISTED,
    STATUS_KICKED_FLAGGED,
)
from core.restore_batch_logic import (
    ACTION_AUTO_JOIN,
    ACTION_CLASSIC_INVITE,
    ACTION_REQUEST_CONSENT,
    ACTION_SKIP_BLACKLISTED,
    MODE_CLASSIC_INVITE,
    MODE_ON_DEMAND_OAUTH,
    plan_restore_action,
)


def test_bannato_viene_sempre_saltato_anche_in_modalita_classica():
    assert plan_restore_action(MODE_CLASSIC_INVITE, STATUS_BANNED_BLACKLISTED, False) == ACTION_SKIP_BLACKLISTED
    assert plan_restore_action(MODE_ON_DEMAND_OAUTH, STATUS_BANNED_BLACKLISTED, False) == ACTION_SKIP_BLACKLISTED


def test_modalita_classica_invita_chiunque_non_sia_bannato():
    assert plan_restore_action(MODE_CLASSIC_INVITE, None, False) == ACTION_CLASSIC_INVITE
    assert plan_restore_action(MODE_CLASSIC_INVITE, STATUS_ACTIVE, False) == ACTION_CLASSIC_INVITE


def test_token_attivo_non_scaduto_viene_riusato_per_l_auto_join():
    assert plan_restore_action(MODE_ON_DEMAND_OAUTH, STATUS_ACTIVE, False) == ACTION_AUTO_JOIN


def test_token_kickato_non_scaduto_viene_comunque_riusato():
    assert plan_restore_action(MODE_ON_DEMAND_OAUTH, STATUS_KICKED_FLAGGED, False) == ACTION_AUTO_JOIN


def test_token_scaduto_richiede_nuovo_consenso():
    assert plan_restore_action(MODE_ON_DEMAND_OAUTH, STATUS_ACTIVE, True) == ACTION_REQUEST_CONSENT


def test_nessun_token_richiede_consenso():
    assert plan_restore_action(MODE_ON_DEMAND_OAUTH, None, False) == ACTION_REQUEST_CONSENT
