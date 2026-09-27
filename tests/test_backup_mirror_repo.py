"""
tests/test_backup_mirror_repo.py
====================================
Test di BackupMirrorRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.backup_mirror_repo import BackupMirrorRepository


@pytest.fixture
def repo(clean_db):
    return BackupMirrorRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_save_mapping_e_get_webhook_url(repo):
    await repo.save_mapping(
        main_guild_id=100,
        backup_guild_id=200,
        channel_webhook_map={10: "https://discord.com/api/webhooks/aaa", 11: "https://discord.com/api/webhooks/bbb"},
    )

    assert await repo.get_webhook_url(10) == "https://discord.com/api/webhooks/aaa"
    assert await repo.get_webhook_url(11) == "https://discord.com/api/webhooks/bbb"


@pytest.mark.asyncio
async def test_get_webhook_url_canale_sconosciuto_restituisce_none(repo):
    assert await repo.get_webhook_url(999) is None


@pytest.mark.asyncio
async def test_save_mapping_sostituisce_la_mappa_precedente(repo):
    await repo.save_mapping(100, 200, {10: "https://vecchio.example/webhook"})
    await repo.save_mapping(100, 300, {20: "https://nuovo.example/webhook"})

    assert await repo.get_webhook_url(10) is None  # il vecchio backup non c'è più
    assert await repo.get_webhook_url(20) == "https://nuovo.example/webhook"


@pytest.mark.asyncio
async def test_save_mapping_vuota_non_solleva(repo):
    await repo.save_mapping(100, 200, {})
    assert await repo.get_webhook_url(10) is None


@pytest.mark.asyncio
async def test_delete_for_main_guild(repo):
    await repo.save_mapping(100, 200, {10: "https://esempio.example/webhook"})
    await repo.delete_for_main_guild(100)

    assert await repo.get_webhook_url(10) is None


@pytest.mark.asyncio
async def test_mappe_di_main_diversi_non_si_toccano(repo):
    # ID canale realistici: due server diversi non condividono mai lo
    # stesso ID (snowflake globale Discord) — save_mapping su un main
    # non deve toccare la mappa di un altro main.
    await repo.save_mapping(100, 200, {10: "https://a.example/webhook"})
    await repo.save_mapping(999, 888, {30: "https://b.example/webhook"})

    assert await repo.get_webhook_url(10) == "https://a.example/webhook"
    assert await repo.get_webhook_url(30) == "https://b.example/webhook"

    # save_mapping su 999 non deve aver cancellato la mappa di 100.
    await repo.save_mapping(999, 888, {30: "https://b2.example/webhook"})
    assert await repo.get_webhook_url(10) == "https://a.example/webhook"
