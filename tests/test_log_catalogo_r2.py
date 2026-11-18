"""
tests/test_log_catalogo_r2.py
=============================
Catalogo log (#119), giro r2log. LOG-010 e LOG-011 le scrive il codice di moderazione nel log di
moderazione (M 1.8): qui si controlla che le prove restino al loro posto.
"""

import importlib

import pytest

PROVE_MODERAZIONE = {
    # LOG-010: scadenza di tempban e mute a ruolo, fine di un lock a tempo
    "tests.test_moderation_tempban_modi": ["test_la_scadenza_scrive_nel_log_di_moderazione"],
    # LOG-011: lock, unlock, slowmode e clear lasciano una riga con chi ha dato il comando
    "tests.test_moderation_clear_filtri": ["test_lock_unlock_slowmode_lasciano_una_riga_di_log", "test_clear_filtra_e_scrive_nel_log"],
}


@pytest.mark.parametrize("modulo", sorted(PROVE_MODERAZIONE))
def test_log010_log011_le_prove_della_moderazione_esistono_ancora(modulo):
    corpo = importlib.import_module(modulo)
    for nome in PROVE_MODERAZIONE[modulo]:
        assert callable(getattr(corpo, nome, None)), f"{modulo}.{nome} e' sparito: LOG-010/LOG-011 non sono piu' provati"
