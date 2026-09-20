"""
tests/test_sticky_message_repo.py
=====================================
Test di StickyMessageRepository contro PostgreSQL reale.
"""

from datetime import datetime, timezone

import pytest

from core.repositories.sticky_message_repo import StickyMessageRepository


@pytest.fixture
def repo(clean_db):
    return StickyMessageRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_get_sticky_inesistente_restituisce_none(repo):
    assert await repo.get_sticky(500) is None


@pytest.mark.asyncio
async def test_set_e_get_sticky(repo):
    await repo.set_sticky(channel_id=500, guild_id=100, message_text="Benvenuto!")
    sticky = await repo.get_sticky(500)
    assert sticky is not None
    assert sticky.guild_id == 100
    assert sticky.message_text == "Benvenuto!"
    assert sticky.last_message_id is None
    assert sticky.last_reposted_at is None


@pytest.mark.asyncio
async def test_set_sticky_due_volte_azzera_lo_stato_di_repost(repo):
    ora = datetime.now(timezone.utc)
    await repo.set_sticky(500, 100, "Primo testo")
    await repo.update_repost_state(500, message_id=999, reposted_at=ora)

    # Un nuovo set_sticky (testo cambiato) deve azzerare lo stato -
    # non ha senso "ricordare" il messaggio del vecchio sticky per uno
    # nuovo con testo diverso.
    await repo.set_sticky(500, 100, "Nuovo testo")

    sticky = await repo.get_sticky(500)
    assert sticky.message_text == "Nuovo testo"
    assert sticky.last_message_id is None
    assert sticky.last_reposted_at is None


@pytest.mark.asyncio
async def test_remove_sticky(repo):
    await repo.set_sticky(500, 100, "Testo")
    rimosso = await repo.remove_sticky(500)
    assert rimosso is True
    assert await repo.get_sticky(500) is None


@pytest.mark.asyncio
async def test_remove_sticky_inesistente_restituisce_false(repo):
    assert await repo.remove_sticky(999) is False


@pytest.mark.asyncio
async def test_update_repost_state(repo):
    ora = datetime.now(timezone.utc)
    await repo.set_sticky(500, 100, "Testo")

    await repo.update_repost_state(500, message_id=12345, reposted_at=ora)

    sticky = await repo.get_sticky(500)
    assert sticky.last_message_id == 12345
    assert sticky.last_reposted_at is not None


@pytest.mark.asyncio
async def test_sticky_non_mischia_canali(repo):
    await repo.set_sticky(500, 100, "Canale A")
    await repo.set_sticky(600, 100, "Canale B")

    sticky_a = await repo.get_sticky(500)
    sticky_b = await repo.get_sticky(600)
    assert sticky_a.message_text == "Canale A"
    assert sticky_b.message_text == "Canale B"
