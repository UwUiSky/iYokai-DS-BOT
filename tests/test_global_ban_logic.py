"""
tests/test_global_ban_logic.py
==================================
Test della logica pura del ban globale (SPEC.md §7.3,
core/global_ban_logic.py) — nessun database, nessun discord.py.
"""

from core.global_ban_logic import should_propagate_ban


def test_propaga_se_entrambi_aderiscono():
    assert should_propagate_ban(
        source_guild_id=1, target_guild_id=2, source_opted_in=True, target_opted_in=True
    ) is True


def test_non_propaga_se_il_target_non_aderisce():
    assert should_propagate_ban(
        source_guild_id=1, target_guild_id=2, source_opted_in=True, target_opted_in=False
    ) is False


def test_non_propaga_se_la_sorgente_non_aderisce():
    assert should_propagate_ban(
        source_guild_id=1, target_guild_id=2, source_opted_in=False, target_opted_in=True
    ) is False


def test_non_propaga_se_nessuno_aderisce():
    assert should_propagate_ban(
        source_guild_id=1, target_guild_id=2, source_opted_in=False, target_opted_in=False
    ) is False


def test_non_propaga_mai_verso_lo_stesso_server():
    # Anche con entrambi i flag True, un server non deve mai
    # "propagare" un ban verso se stesso — l'utente è già bannato lì.
    assert should_propagate_ban(
        source_guild_id=1, target_guild_id=1, source_opted_in=True, target_opted_in=True
    ) is False
