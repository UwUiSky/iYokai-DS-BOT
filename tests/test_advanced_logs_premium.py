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
    log_event = AsyncMock()
    monkeypatch.setattr(event_log_repo, "log_event", log_event)
    yield db, log_event
    db._modules_cache.clear()
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
