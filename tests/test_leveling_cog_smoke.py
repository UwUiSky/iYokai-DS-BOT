"""
tests/test_leveling_cog_smoke.py
===================================
Smoke test del cog livelli/economia. Oltre al solito controllo di
caricamento e registrazione premium, verifica che:
- on_message compaia in bot.extra_events (stessa lezione già nota:
  serve il decorator @commands.Cog.listener())
- il task periodico _voice_xp_tick si avvii senza sollevare
  eccezioni al caricamento del cog (avviato in __init__, con
  before_loop che aspetta bot.wait_until_ready() — qui verifichiamo
  solo che l'avvio in sé non fallisca, non un giro reale del task,
  che richiederebbe server e canali vocali veri)
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.leveling.leveling import MODULE_LEVELING, setup as leveling_setup


async def test_leveling_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await leveling_setup(bot)

    cog = bot.get_cog("LevelingCog")
    assert cog is not None

    module = registry.get(MODULE_LEVELING)
    assert module is not None
    assert module.premium_capable is False

    assert "on_message" in bot.extra_events

    comandi = {c.name for c in bot.tree.get_commands()}
    assert {"rank", "balance", "daily", "work", "pay", "leaderboard"} <= comandi

    level_roles_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "level-roles":
            level_roles_group = command
            break
    assert level_roles_group is not None
    assert {"add", "remove", "list"} <= {c.name for c in level_roles_group.commands}

    # Il task periodico deve essere avviato (non sollevare eccezioni
    # all'avvio del cog) — before_loop attende bot.wait_until_ready(),
    # quindi non gira davvero qui, ma deve risultare "in esecuzione"
    # nel senso di discord.py (task registrato, in attesa).
    assert cog._voice_xp_tick.is_running() is True

    # Pulizia: fermiamo il task per non lasciarlo agganciato
    # all'event loop dopo la fine del test.
    cog._voice_xp_tick.cancel()
