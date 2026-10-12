"""
NF-04 (#19): entrata e uscita del bot da un server si registrano; il lavoro
giornaliero parte con gli altri servizi e si ferma con loro.
"""

import pytest

from tests.test_main_bot import _FakeGuildForBlacklistCheck, _collega_singleton_per_test


@pytest.fixture
def ambiente(monkeypatch, clean_db):
    import core.database as database_module
    import main as main_module
    from core.repositories.guild_presence_repo import GuildPresenceRepository

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    repo = GuildPresenceRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(main_module, "guild_presence_repo", repo)
    return main_module, repo


@pytest.mark.asyncio
async def test_on_guild_remove_avvia_il_conto_dei_90_giorni(ambiente):
    main_module, repo = ambiente
    bot = main_module.iYokaiBot()
    await repo.segna_entrato(321)

    await bot.on_guild_remove(_FakeGuildForBlacklistCheck(321))

    assert (await repo.get(321))["left_at"] is not None


@pytest.mark.asyncio
async def test_un_errore_nella_registrazione_non_rompe_l_evento(ambiente, monkeypatch):
    main_module, repo = ambiente

    async def rotta(guild_id, quando=None):
        raise RuntimeError("database giù")

    monkeypatch.setattr(repo, "segna_uscito", rotta)
    bot = main_module.iYokaiBot()

    await bot.on_guild_remove(_FakeGuildForBlacklistCheck(321))  # non solleva


@pytest.mark.asyncio
async def test_on_guild_join_azzera_il_conto_se_il_bot_rientra(ambiente, monkeypatch):
    main_module, repo = ambiente
    from core.repositories.blacklist_repo import BlacklistRepository

    monkeypatch.setattr(
        main_module, "blacklist_repo", BlacklistRepository(pool_provider=lambda: repo._pool)
    )
    bot = main_module.iYokaiBot()

    async def senza_benvenuto(guild):
        return None

    monkeypatch.setattr(bot, "_send_welcome_message", senza_benvenuto)
    await repo.segna_uscito(321)

    await bot.on_guild_join(_FakeGuildForBlacklistCheck(321))

    assert (await repo.get(321))["left_at"] is None


def test_la_retention_fa_parte_dei_servizi_periodici():
    import main as main_module
    from core.retention_worker import retention_worker

    assert retention_worker in main_module._servizi_periodici()
