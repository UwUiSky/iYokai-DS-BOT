"""
tests/test_automod_cog_smoke.py
==================================
Smoke test del cog AutoMod: caricamento reale in un Bot, registrazione
premium, parametri dei comandi leggibili da discord.py.
"""

import discord
from discord.ext import commands

from core.premium import registry
from cogs.automod.automod import MODULE_AUTOMOD, setup as automod_setup


async def test_automod_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await automod_setup(bot)

    assert bot.get_cog("AutomodCog") is not None

    module = registry.get(MODULE_AUTOMOD)
    assert module is not None
    assert module.premium_capable is False  # sempre gratis, come da schema

    automod_group = bot.tree.get_command("automod")
    assert automod_group is not None

    parole = automod_group.get_command("parole")
    filtri = automod_group.get_command("filtri")
    esenzioni = automod_group.get_command("esenzioni")
    assert {c.name for c in parole.commands} == {"add", "remove", "list"}
    assert {"invites"} <= {c.name for c in filtri.commands}
    assert {"sync", "mute-duration", "log-channel", "status"} <= {c.name for c in automod_group.commands}
    assert {c.name for c in filtri.commands} == {
        "invites",
        "anti-link-mode",
        "anti-link-domain",
        "anti-spam-messages",
        "anti-spam-emoji",
        "anti-spam-sticker",
        "anti-caps",
        "anti-zalgo",
        "phishing",
        "forma-testo",
        "anti-mention",
        "anti-attachment",
        "actions-set",
    }
    assert {c.name for c in esenzioni.commands} == {
        "channel-add",
        "channel-remove",
        "role-add",
        "role-remove",
    }

    add_cmd = parole.get_command("add")
    assert "word" in [p.name for p in add_cmd.parameters]

    invites_cmd = filtri.get_command("invites")
    assert "enabled" in [p.name for p in invites_cmd.parameters]

    anti_caps_cmd = filtri.get_command("anti-caps")
    assert {"enabled", "percent", "min_length"} <= {p.name for p in anti_caps_cmd.parameters}
    await bot.remove_cog("AutomodCog")
