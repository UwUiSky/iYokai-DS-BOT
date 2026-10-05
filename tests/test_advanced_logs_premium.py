"""
tests/test_advanced_logs_premium.py
===================================
M 3.14 (#134): il Logging Avanzato controlla il premium.

Quando l'owner del bot rende premium il modulo, un server che non lo ha
sbloccato non riceve più questi log (nessuna riga nel database, nessun
messaggio nel canale), anche se il modulo risulta acceso. Finché il
modulo non è premium non cambia niente per nessuno.

Sblocco vero di core/premium.py contro il database vero.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.logging.advanced_logs as modulo
import core.premium as modulo_premium
from core.premium import registry
from core.repositories.event_log_repo import event_log_repo
from core.soundboard_log_service import SoundboardLogService
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel

GUILD_ID = 100
CANALE_LOG = 777


class _ConfigSenzaSbloccoAlpha:
    PREMIUM_ALPHA_UNLOCK_ALL = False
    MAIN_GUILD_ID = 987654321


@pytest.fixture
def ambiente(monkeypatch, clean_db, reset_premium_registry):
    import core.database as database_module

    db = database_module.db
    monkeypatch.setattr(db, "_pool", clean_db)
    db._modules_cache.clear()
    monkeypatch.setattr(modulo_premium, "config", _ConfigSenzaSbloccoAlpha())
    modulo._premium_cache.clear()
    log_event = AsyncMock()
    monkeypatch.setattr(event_log_repo, "log_event", log_event)
    yield db, log_event
    db._modules_cache.clear()
    modulo._premium_cache.clear()
    if registry.get(modulo.MODULE_LOGGING_ADVANCED) is not None:
        registry.set_module_premium(modulo.MODULE_LOGGING_ADVANCED, False)


async def _cog_acceso(db):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await modulo.setup(bot)
    await db.set_module_active_for_guild(GUILD_ID, modulo.MODULE_LOGGING_ADVANCED, True)
    await db.set_guild_setting(GUILD_ID, modulo.SETTING_LOG_CHANNEL, CANALE_LOG)
    return bot, bot.get_cog("AdvancedLogsCog")


def _server_con_canale():
    server = fake_guild(GUILD_ID, name="Prima")
    canale = fake_text_channel(CANALE_LOG)
    server.get_channel.side_effect = lambda i: canale if i == CANALE_LOG else None
    return server, canale


def _server_rinominato(prima):
    dopo = fake_guild(GUILD_ID, name="Dopo")
    dopo.get_channel.side_effect = prima.get_channel.side_effect
    return dopo


async def test_non_premium_i_log_avanzati_funzionano(ambiente):
    db, log_event = ambiente
    bot, cog = await _cog_acceso(db)
    prima, canale = _server_con_canale()

    await cog.on_guild_update(prima, _server_rinominato(prima))

    log_event.assert_awaited_once()
    canale.send.assert_awaited_once()
    await bot.close()


async def test_premium_non_sbloccato_i_log_avanzati_non_scrivono(ambiente):
    db, log_event = ambiente
    bot, cog = await _cog_acceso(db)
    registry.set_module_premium(modulo.MODULE_LOGGING_ADVANCED, True)
    prima, canale = _server_con_canale()

    await cog.on_guild_update(prima, _server_rinominato(prima))
    await cog.on_member_join(fake_member(user_id=5))

    log_event.assert_not_awaited()
    canale.send.assert_not_awaited()
    await bot.close()


async def test_premium_sbloccato_i_log_avanzati_scrivono(ambiente):
    db, log_event = ambiente
    bot, cog = await _cog_acceso(db)
    registry.set_module_premium(modulo.MODULE_LOGGING_ADVANCED, True)
    await db.add_guild_to_whitelist(GUILD_ID, added_by=1, reason="test")
    prima, canale = _server_con_canale()

    await cog.on_guild_update(prima, _server_rinominato(prima))

    log_event.assert_awaited_once()
    canale.send.assert_awaited_once()
    await bot.close()


async def test_premium_non_sbloccato_il_servizio_soundboard_non_legge_l_audit_log(ambiente):
    db, log_event = ambiente
    bot, _ = await _cog_acceso(db)
    registry.set_module_premium(modulo.MODULE_LOGGING_ADVANCED, True)
    server, _ = _server_con_canale()
    server.audit_logs = MagicMock(side_effect=AssertionError("audit log letto"))
    bot_finto = MagicMock(guilds=[server])
    bot_finto.get_guild.return_value = None  # nessun boost sul server principale

    await SoundboardLogService().tick(bot_finto)

    server.audit_logs.assert_not_called()
    await bot.close()


def test_nessun_listener_controlla_solo_il_modulo_acceso():
    """Un listener nuovo che dimentica il premium non passa inosservato."""
    sorgente = inspect.getsource(modulo.AdvancedLogsCog)
    assert "is_module_active_for_guild" not in sorgente
    assert sorgente.count("logging_avanzato_attivo(") >= 15


# ====================================================================
# Cache breve: un evento dietro l'altro non rifà le query del premium
# ====================================================================
@pytest.fixture
def conta_giri(monkeypatch):
    chiamate = []
    originale = modulo.premium_sbloccato

    async def _conta(*args, **kwargs):
        chiamate.append(args)
        return await originale(*args, **kwargs)

    monkeypatch.setattr(modulo, "premium_sbloccato", _conta)
    return chiamate


async def test_cinque_eventi_fanno_un_solo_giro_di_query_del_premium(ambiente, conta_giri):
    db, _ = ambiente
    bot, _ = await _cog_acceso(db)
    registry.set_module_premium(modulo.MODULE_LOGGING_ADVANCED, True)

    risultati = [await modulo.logging_avanzato_attivo(GUILD_ID, bot) for _ in range(5)]

    assert risultati == [False] * 5
    assert len(conta_giri) == 1
    await bot.close()


async def test_dopo_la_scadenza_il_premium_si_rilegge(ambiente, conta_giri, monkeypatch):
    db, _ = ambiente
    bot, _ = await _cog_acceso(db)
    registry.set_module_premium(modulo.MODULE_LOGGING_ADVANCED, True)
    adesso = [1000.0]
    monkeypatch.setattr(modulo, "_monotonic", lambda: adesso[0])

    assert await modulo.logging_avanzato_attivo(GUILD_ID, bot) is False
    await db.add_guild_to_whitelist(GUILD_ID, added_by=1, reason="test")
    adesso[0] += modulo.PREMIUM_CACHE_TTL_SECONDS - 1
    assert await modulo.logging_avanzato_attivo(GUILD_ID, bot) is False  # ancora in cache
    assert len(conta_giri) == 1

    adesso[0] += 2
    assert await modulo.logging_avanzato_attivo(GUILD_ID, bot) is True
    assert len(conta_giri) == 2
    await bot.close()


async def test_modulo_spento_non_usa_ne_riempie_la_cache(ambiente, conta_giri):
    db, _ = ambiente
    bot, _ = await _cog_acceso(db)
    await db.set_module_active_for_guild(GUILD_ID, modulo.MODULE_LOGGING_ADVANCED, False)
    registry.set_module_premium(modulo.MODULE_LOGGING_ADVANCED, True)

    assert await modulo.logging_avanzato_attivo(GUILD_ID, bot) is False

    assert conta_giri == []
    assert len(modulo._premium_cache) == 0
    await bot.close()


def test_la_cache_ha_il_tetto_di_10000_voci():
    assert modulo._premium_cache.max_size == 10_000
