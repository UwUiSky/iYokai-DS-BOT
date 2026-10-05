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


@pytest.mark.parametrize("scrittura", ["set_config", "set_panel_message"])
async def test_lettura_nata_durante_la_scrittura_non_cacha_il_vecchio(clean_db, scrittura):
    # La lettura parte DOPO l'invalidazione iniziale e finisce DOPO il
    # commit: solo l'invalidazione dopo la scrittura la ferma.
    import asyncio

    class _Pool(_PoolContaLetture):
        def __init__(self, pool) -> None:
            super().__init__(pool)
            self.scrittura_ferma = asyncio.Event()
            self.scrittura_via = asyncio.Event()
            self.lettura_ferma = asyncio.Event()
            self.lettura_via = asyncio.Event()
            self.attivo = False

        async def execute(self, query, *args):
            if self.attivo and "INSERT INTO verify_config" in query:
                self.scrittura_ferma.set()
                await self.scrittura_via.wait()
            return await self._pool.execute(query, *args)

        async def fetchrow(self, query, *args):
            riga = await self._pool.fetchrow(query, *args)  # ancora il vecchio
            if self.attivo and "verify_config" in query:
                self.lettura_ferma.set()
                await self.lettura_via.wait()
            return riga

    pool = _Pool(clean_db)
    repo = VerifyRepository(pool_provider=lambda: pool)
    await repo.set_config(100, "button", 555, 0, 0, False, None)
    pool.attivo = True

    if scrittura == "set_config":
        nuova = asyncio.create_task(repo.set_config(100, "reaction", 777, 0, 0, False, None))
    else:
        nuova = asyncio.create_task(repo.set_panel_message(100, 11, 22))
    await pool.scrittura_ferma.wait()          # invalidazione iniziale già fatta
    lettura = asyncio.create_task(repo.get_config(100))
    await pool.lettura_ferma.wait()            # ha letto il valore vecchio
    pool.scrittura_via.set()
    await nuova                                # commit + invalidazione finale
    pool.lettura_via.set()
    await lettura

    config = await repo.get_config(100)
    if scrittura == "set_config":
        assert config.verified_role_id == 777
    else:
        assert (config.panel_channel_id, config.panel_message_id) == (11, 22)
