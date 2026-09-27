"""
tests/test_backup_snapshot_logic.py
=======================================
Test di is_eligible_for_snapshot (SPEC.md §11.10) — logica pura.
"""

from core.backup_snapshot_logic import is_eligible_for_snapshot


def test_un_bot_non_e_mai_incluso():
    assert is_eligible_for_snapshot(is_bot=True, member_role_ids={1, 2}, verified_role_id=1) is False


def test_membro_con_il_ruolo_verificato_e_incluso():
    assert is_eligible_for_snapshot(is_bot=False, member_role_ids={1, 2}, verified_role_id=1) is True


def test_membro_senza_il_ruolo_verificato_non_e_incluso():
    assert is_eligible_for_snapshot(is_bot=False, member_role_ids={2, 3}, verified_role_id=1) is False


def test_server_senza_verify_configurato_include_chiunque_non_sia_bot():
    assert is_eligible_for_snapshot(is_bot=False, member_role_ids=set(), verified_role_id=None) is True


def test_server_senza_verify_configurato_esclude_comunque_i_bot():
    assert is_eligible_for_snapshot(is_bot=True, member_role_ids=set(), verified_role_id=None) is False
