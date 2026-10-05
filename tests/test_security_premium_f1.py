"""
tests/test_security_premium_f1.py
=================================
I moduli di sicurezza "premium" controllano davvero il premium
(REVIEW §4 e §12, voce 3.3): spam-trap, anti-nuke, anti-raid,
ban globale e heatmap dei permessi.

Quando l'owner del bot rende premium un modulo, un server che non lo
ha sbloccato:
- si vede rifiutare i comandi del modulo;
- non riceve più l'azione automatica del modulo (i listener si fermano).
Finché il modulo non è premium non cambia niente per nessuno.

Il cog è caricato in un `commands.Bot` vero (non collegato); lo sblocco
è quello vero di core/premium.py contro il database vero.
"""

import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import core.premium as modulo_premium
from core.premium import ModuleNotUnlockedError, registry
from core.repositories.security_repo import security_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

GUILD_ID = 100

MODULI = {
    "spam_trap": "cogs.security.spam_trap",
    "anti_nuke": "cogs.security.anti_nuke",
    "anti_raid": "cogs.security.anti_raid",
    "global_ban": "cogs.security.global_ban",
    "permission_heatmap": "cogs.security.permission_heatmap",
}

# Uscire dalla rete dei ban globali deve restare sempre possibile.
SEMPRE_PERMESSI = {"global-ban disable"}


class _ConfigSenzaSbloccoAlpha:
    PREMIUM_ALPHA_UNLOCK_ALL = False
    MAIN_GUILD_ID = 987654321


@pytest.fixture
def ambiente(monkeypatch, clean_db, reset_premium_registry):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    monkeypatch.setattr(modulo_premium, "config", _ConfigSenzaSbloccoAlpha())
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    yield database_module.db
    database_module.db._modules_cache.clear()
    # reset_premium_registry rimette a posto l'elenco dei moduli, non
    # la loro spunta "premium": la si spegne qui, o resterebbe accesa
    # per i test che vengono dopo.
    for nome_modulo in MODULI:
        if registry.get(nome_modulo) is not None:
            registry.set_module_premium(nome_modulo, False)


async def _bot_con(nome_modulo: str) -> commands.Bot:
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await importlib.import_module(MODULI[nome_modulo]).setup(bot)
    return bot


def _comandi(bot: commands.Bot) -> list[app_commands.Command]:
    return [
        comando
        for comando in bot.tree.walk_commands()
        if isinstance(comando, app_commands.Command)
    ]


async def _passa_i_controlli(comando: app_commands.Command, bot: commands.Bot) -> None:
    """Esegue i controlli del comando come fa discord.py prima di chiamarlo."""
    interazione = fake_interaction(
        guild=fake_guild(GUILD_ID), permissions=discord.Permissions.all()
    )
    interazione.client = bot
    for controllo in comando.checks:
        await discord.utils.maybe_coroutine(controllo, interazione)


@pytest.mark.parametrize("nome_modulo", sorted(MODULI))
async def test_modulo_premium_non_sbloccato_i_comandi_rifiutano(ambiente, nome_modulo):
    bot = await _bot_con(nome_modulo)
    registry.set_module_premium(nome_modulo, True)
    comandi = _comandi(bot)
    assert comandi

    for comando in comandi:
        if comando.qualified_name in SEMPRE_PERMESSI:
            await _passa_i_controlli(comando, bot)
            continue
        with pytest.raises(ModuleNotUnlockedError):
            await _passa_i_controlli(comando, bot)
    await bot.close()


@pytest.mark.parametrize("nome_modulo", sorted(MODULI))
async def test_modulo_premium_sbloccato_i_comandi_passano(ambiente, nome_modulo):
    bot = await _bot_con(nome_modulo)
    registry.set_module_premium(nome_modulo, True)
    await ambiente.add_guild_to_whitelist(GUILD_ID, added_by=1, reason="test")

    for comando in _comandi(bot):
        await _passa_i_controlli(comando, bot)
    await bot.close()


@pytest.mark.parametrize("nome_modulo", sorted(MODULI))
async def test_modulo_non_premium_i_comandi_passano(ambiente, nome_modulo):
    bot = await _bot_con(nome_modulo)

    for comando in _comandi(bot):
        await _passa_i_controlli(comando, bot)
    await bot.close()


# ====================================================================
# I listener: senza sblocco il modulo non agisce
# ====================================================================
async def _raid(cog, server: MagicMock) -> list[MagicMock]:
    membri = []
    for numero in range(3):
        membro = fake_member(user_id=500 + numero, name=f"Persona{numero}")
        membro.guild = server
        membro.created_at = datetime.now(timezone.utc) - timedelta(days=400)
        membro.avatar = MagicMock()
        await cog.on_member_join(membro)
        membri.append(membro)
    return membri


async def _anti_raid_configurato(ambiente):
    import cogs.security.anti_raid as anti_raid

    await ambiente.set_module_active_for_guild(GUILD_ID, anti_raid.MODULE_ANTI_RAID, True)
    bot = await _bot_con("anti_raid")
    cog = bot.get_cog("AntiRaidCog")
    server = fake_guild(GUILD_ID, owner_id=1)
    server.owner = fake_member(user_id=1)
    server.verification_level = discord.VerificationLevel.medium
    interazione = fake_interaction(guild=server)
    await cog.enable.callback(cog, interazione, True)
    await cog.join_rate.callback(cog, interazione, 0, 60)
    await cog.lockdown_action.callback(
        cog, interazione, app_commands.Choice(name="verification", value="verification")
    )
    return bot, cog, server


async def test_anti_raid_premium_non_sbloccato_non_agisce(ambiente):
    bot, cog, server = await _anti_raid_configurato(ambiente)
    registry.set_module_premium("anti_raid", True)

    await _raid(cog, server)

    server.edit.assert_not_awaited()
    server.owner.send.assert_not_awaited()
    await bot.close()


async def test_anti_raid_premium_sbloccato_agisce(ambiente):
    bot, cog, server = await _anti_raid_configurato(ambiente)
    registry.set_module_premium("anti_raid", True)
    await ambiente.add_guild_to_whitelist(GUILD_ID, added_by=1, reason="test")

    await _raid(cog, server)

    server.edit.assert_awaited()
    await bot.close()


async def test_anti_nuke_premium_non_sbloccato_non_legge_il_registro(ambiente):
    import cogs.security.anti_nuke as anti_nuke

    await ambiente.set_module_active_for_guild(GUILD_ID, anti_nuke.MODULE_ANTI_NUKE, True)
    bot = await _bot_con("anti_nuke")
    cog = bot.get_cog("AntiNukeCog")
    server = fake_guild(GUILD_ID, owner_id=1)
    await cog.enable.callback(cog, fake_interaction(guild=server), True)
    registry.set_module_premium("anti_nuke", True)
    canale = create_autospec(discord.TextChannel, instance=True)
    canale.id = 7001
    canale.name = "generale"
    canale.guild = server

    await cog.on_guild_channel_delete(canale)

    server.audit_logs.assert_not_called()
    await bot.close()


async def test_ban_globale_non_si_propaga_se_il_modulo_e_premium_e_non_sbloccato(ambiente):
    import cogs.security.global_ban as global_ban

    sorgente = fake_guild(GUILD_ID, "Alpha")
    bersaglio = fake_guild(200, "Beta")
    for server in (sorgente, bersaglio):
        await ambiente.set_module_active_for_guild(server.id, global_ban.MODULE_GLOBAL_BAN, True)
    bot = create_autospec(commands.Bot, instance=True)
    bot.guilds = [sorgente, bersaglio]
    bot.get_guild.return_value = None
    # Il cog vero registra il modulo, come all'avvio del bot.
    bot_con_il_cog = await _bot_con("global_ban")
    registry.set_module_premium("global_ban", True)

    propagati = await global_ban.propagate_ban(bot, sorgente, 42, "Spam trap triggered")

    assert propagati == []
    bersaglio.ban.assert_not_awaited()
    await bot_con_il_cog.close()


async def test_ban_globale_si_propaga_se_il_modulo_non_e_premium(ambiente):
    import cogs.security.global_ban as global_ban

    sorgente = fake_guild(GUILD_ID, "Alpha")
    bersaglio = fake_guild(200, "Beta")
    for server in (sorgente, bersaglio):
        await ambiente.set_module_active_for_guild(server.id, global_ban.MODULE_GLOBAL_BAN, True)
    bot = create_autospec(commands.Bot, instance=True)
    bot.guilds = [sorgente, bersaglio]
    bot.get_guild.return_value = None

    propagati = await global_ban.propagate_ban(bot, sorgente, 42, "Spam trap triggered")

    assert propagati == [200]
    bersaglio.ban.assert_awaited_once()
