"""
tests/test_backup_creator_bot_smoke.py
==========================================
Smoke test di BackupCreatorBot — un'istanza si crea correttamente,
non ha comandi propri (esiste solo per creare/clonare server).
"""

from core.backup_creator_bot import BackupCreatorBot


def test_backup_creator_bot_si_istanzia_senza_comandi_propri():
    creator = BackupCreatorBot()

    assert list(creator.tree.get_commands()) == []


def test_backup_creator_bot_ha_allowed_mentions_sicuro():
    # SEC-7
    creator = BackupCreatorBot()
    am = creator.allowed_mentions
    assert am.everyone is False
    assert am.roles is False
    assert am.users is True
    assert am.replied_user is False
