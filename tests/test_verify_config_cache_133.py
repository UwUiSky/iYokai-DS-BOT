"""
tests/test_verify_config_cache_133.py
=====================================
Issue #133, verifica: la configurazione è in una cache con tetto
(core/bounded_cache.py). La seconda lettura non va al database; ogni
scrittura la aggiorna; la cache non cresce oltre il tetto.
"""

from unittest.mock import AsyncMock

import pytest

from core.repositories.verify_repo import VerifyRepository


@pytest.fixture
def repo(clean_db):
    return VerifyRepository(pool_provider=lambda: clean_db)


class _PoolContaLetture:
    """Il pool vero, ma conta quante letture della configurazione fa."""

    def __init__(self, pool) -> None:
        self._pool = pool
        self.letture = 0

    async def fetchrow(self, query, *args):
        if "verify_config" in query:
            self.letture += 1
        return await self._pool.fetchrow(query, *args)

    def __getattr__(self, nome):
        return getattr(self._pool, nome)


async def test_seconda_lettura_non_va_al_database(clean_db):
    pool = _PoolContaLetture(clean_db)
    repo = VerifyRepository(pool_provider=lambda: pool)
    await repo.set_config(100, "button", 555, 0, 0, False, None)

    primo = await repo.get_config(100)
    secondo = await repo.get_config(100)

    assert primo == secondo
    assert pool.letture == 1


async def test_set_config_aggiorna_la_cache(clean_db):
    pool = _PoolContaLetture(clean_db)
    repo = VerifyRepository(pool_provider=lambda: pool)
    assert (await repo.get_config(100)).verified_role_id is None  # default in cache

    await repo.set_config(100, "reaction", 777, 3, 1, True, 9)

    config = await repo.get_config(100)
    assert (config.method, config.verified_role_id, config.captcha_enabled) == ("reaction", 777, True)


async def test_set_panel_message_aggiorna_la_cache(repo):
    await repo.set_config(100, "button", 555, 0, 0, False, None)
    await repo.get_config(100)

    await repo.set_panel_message(100, 11, 22)

    config = await repo.get_config(100)
    assert (config.panel_channel_id, config.panel_message_id) == (11, 22)


async def test_la_cache_ha_un_tetto(repo):
    from core.repositories import verify_repo as modulo

    assert repo._config_cache.max_size == modulo.MAX_CONFIG_IN_CACHE
    assert 0 < modulo.MAX_CONFIG_IN_CACHE <= 10_000


async def test_lettura_lenta_non_rimette_in_cache_il_valore_vecchio(clean_db):
    import asyncio

    class _PoolLento(_PoolContaLetture):
        def __init__(self, pool) -> None:
            super().__init__(pool)
            self.letto = asyncio.Event()
            self.via = asyncio.Event()

        async def fetchrow(self, query, *args):
            riga = await self._pool.fetchrow(query, *args)  # valore VECCHIO
            if "verify_config" in query and not self.via.is_set():
                self.letto.set()
                await self.via.wait()
            return riga

    pool = _PoolLento(clean_db)
    repo = VerifyRepository(pool_provider=lambda: pool)
    await repo.set_config(100, "button", 555, 0, 0, False, None)

    lettura = asyncio.create_task(repo.get_config(100))
    await pool.letto.wait()
    await repo.set_config(100, "reaction", 777, 0, 0, False, None)  # corsa
    pool.via.set()
    await lettura

    assert (await repo.get_config(100)).verified_role_id == 777
