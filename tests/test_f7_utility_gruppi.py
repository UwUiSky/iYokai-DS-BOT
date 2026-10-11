"""
tests/test_f7_utility_gruppi.py
===============================
Gli strumenti per tutti stanno in /utility (aperto a tutti, solo server);

Funzioni coperte: NF-05 (issue #76)
"""

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility.ping import setup as ping_setup
from cogs.utility.poll import setup as poll_setup
from cogs.utility.reminders import setup as reminders_setup
from cogs.utility.server_stats import setup as stats_setup
from cogs.utility.snipe import setup as snipe_setup
from core.command_groups import GRUPPI
from tests.support.percorsi import percorsi_del_gruppo

ATTESI = {"ping", "poll", "serverstats", "reactionsnipe", "reminder set", "reminder list", "reminder cancel"}
VECCHI_TOP = {"ping", "poll", "serverstats", "reactionsnipe", "reminder"}


async def test_utility_ha_i_comandi_giusti_ed_e_aperto_a_tutti():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    for setup in (ping_setup, poll_setup, stats_setup, snipe_setup, reminders_setup):
        await setup(bot)
    gruppo = GRUPPI["utility"]
    assert ATTESI <= percorsi_del_gruppo("utility")
    assert gruppo.livello is None and gruppo.default_permissions is None
    assert gruppo.guild_only is True
    assert len(gruppo.commands) <= 25
    nomi_top = {c.name for c in bot.tree.get_commands()}
    assert not VECCHI_TOP & nomi_top


async def test_nomi_e_descrizioni_di_utility_sono_nei_limiti():
    for nome, figlio in ((c.name, c) for c in GRUPPI["utility"].commands):
        assert len(nome) <= 32
        if not isinstance(figlio, app_commands.Group):
            assert len(figlio.description) <= 100 and not figlio.description.startswith("[")
