"""
tests/test_premium_invalidazione.py
===================================
#145: un punto unico per dimenticare il verdetto premium in memoria.
Whitelist, cassa, abbonamenti e flag del modulo lo chiamano: lo sblocco
o la revoca valgono subito, non dopo i 60 secondi del TTL.
"""

import pytest

import core.premium_cache as cache
from core.premium import PremiumModule, registry


@pytest.fixture
def chiamate(monkeypatch):
    monkeypatch.setattr(cache, "_invalidatori", [])
    registrate: list = []
    cache.registra_invalidatore(registrate.append)
    return registrate


def test_invalida_chiama_gli_invalidatori_registrati(chiamate):
    cache.invalida_cache_premium(5)
    cache.invalida_cache_premium()
    assert chiamate == [5, None]


def test_registrare_due_volte_non_duplica(monkeypatch):
    monkeypatch.setattr(cache, "_invalidatori", [])
    visti: list = []
    cache.registra_invalidatore(visti.append)
    cache.registra_invalidatore(visti.append)
    cache.invalida_cache_premium(1)
    assert visti == [1]


def test_un_invalidatore_rotto_non_ferma_gli_altri(monkeypatch):
    monkeypatch.setattr(cache, "_invalidatori", [])
    visti: list = []

    def rotto(_):
        raise RuntimeError("boom")

    cache.registra_invalidatore(rotto)
    cache.registra_invalidatore(visti.append)
    cache.invalida_cache_premium(1)
    assert visti == [1]


def test_cambio_flag_del_modulo_invalida_tutti(chiamate, reset_premium_registry):
    registry.register(PremiumModule("prova_145", "Prova", "x", category="utility"))
    registry.set_module_premium("prova_145", True)
    assert chiamate == [None]


@pytest.mark.asyncio
async def test_whitelist_aggiunta_e_tolta_invalidano_quel_server(chiamate, clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await database_module.db.add_guild_to_whitelist(42, 1, "prova")
    await database_module.db.remove_guild_from_whitelist(42)
    assert chiamate == [42, 42]


@pytest.mark.asyncio
async def test_abbonamento_concesso_e_revocato_invalidano(chiamate, clean_db):
    from core.repositories.module_subscription_repo import ModuleSubscriptionRepository

    repo = ModuleSubscriptionRepository(pool_provider=lambda: clean_db)
    await repo.grant(42, "logging_advanced", 30)
    await repo.revoke(42, "logging_advanced")
    assert chiamate == [42, 42]


@pytest.mark.asyncio
async def test_acquisto_cassa_invalida_dopo_il_commit(chiamate, clean_db, monkeypatch):
    import core.database as database_module
    from datetime import datetime, timezone
    from core.repositories.guild_premium_repo import guild_premium_repo
    from core.repositories.guild_chest_repo import guild_chest_repo  # noqa: F401
    import core.premium_purchase_service as servizio

    monkeypatch.setattr(database_module.db, "_pool", clean_db)

    async def _spend(conn, guild_id, costo, motivo):
        return True

    async def _record(guild_id, tier, costo, now, conn=None):
        assert chiamate == []  # ancora dentro la transazione: nessuna invalidazione
        return datetime(2030, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(servizio, "spend_in", _spend)
    monkeypatch.setattr(servizio.guild_premium_repo, "record_purchase", _record)
    await database_module.db.ensure_guild_exists(42)
    monkeypatch.setattr(servizio, "is_tier_time_unlocked", lambda *a, **k: True)
    risultato = await servizio.purchase_premium_tier(42, 1, 10)
    assert risultato.outcome == servizio.PurchaseOutcome.SUCCESS
    assert chiamate == [42]


def test_i_log_avanzati_si_registrano_come_invalidatore():
    import cogs.logging.advanced_logs as modulo

    modulo._premium_cache.set(7, (10**12, True))
    cache.invalida_cache_premium(7)
    assert modulo._premium_cache.get(7) is None
