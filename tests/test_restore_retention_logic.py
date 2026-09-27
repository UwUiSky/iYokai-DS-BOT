"""
tests/test_restore_retention_logic.py
=========================================
Test di was_recently_kicked (SPEC.md §11.11) — logica pura.
"""

from datetime import datetime, timedelta, timezone

from core.restore_retention_logic import was_recently_kicked


class _VoceAudit:
    def __init__(self, target_id: int, created_at: datetime) -> None:
        self.target_id = target_id
        self.created_at = created_at


def test_voce_recente_per_lo_stesso_utente_e_un_kick():
    ora = datetime.now(timezone.utc)
    voci = [_VoceAudit(target_id=1, created_at=ora - timedelta(seconds=2))]
    assert was_recently_kicked(voci, user_id=1, now=ora) is True


def test_voce_per_un_altro_utente_non_conta():
    ora = datetime.now(timezone.utc)
    voci = [_VoceAudit(target_id=2, created_at=ora - timedelta(seconds=2))]
    assert was_recently_kicked(voci, user_id=1, now=ora) is False


def test_voce_troppo_vecchia_non_conta():
    ora = datetime.now(timezone.utc)
    voci = [_VoceAudit(target_id=1, created_at=ora - timedelta(minutes=5))]
    assert was_recently_kicked(voci, user_id=1, now=ora, within_seconds=10.0) is False


def test_nessuna_voce_non_e_un_kick():
    ora = datetime.now(timezone.utc)
    assert was_recently_kicked([], user_id=1, now=ora) is False
