"""
tests/test_owner_premium_cog_smoke.py
=====================================
Il cog owner mette i suoi 25 comandi nei 4 sottogruppi di /owner
(premium, blacklist, cog, system) e /owner non entra nell'albero globale:
si registra solo nel server dell'owner (registra_owner, mappa F7 §5).
Funzioni coperte: NF-05 (issue #76)
"""

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility.owner_premium import setup as owner_premium_setup
from core import command_groups as cg
from core.command_access import Livello

ATTESI = {
    "premium": {
        "list", "toggle", "grant", "revoke", "subscriptions", "status-all", "panel",
        "whitelist-add", "whitelist-remove", "whitelist-list",
    },
    "blacklist": {
        "utente-add", "utente-remove", "utente-list", "server-add", "server-remove", "server-list",
    },
    "cog": {"load", "unload", "reload"},
    "system": {"eval", "shell", "memory-status", "leave-guild", "announce", "stats"},
}


async def test_owner_premium_cog_mette_i_comandi_nei_sottogruppi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await owner_premium_setup(bot)
    try:
        assert bot.get_cog("OwnerPremiumCog") is not None
        owner = cg.GRUPPI["owner"]
        assert owner.livello is Livello.OWNER
        trovati = {}
        for figlio in owner.commands:
            assert isinstance(figlio, app_commands.Group), f"/owner {figlio.name} dovrebbe stare in un sottogruppo"
            trovati[figlio.name] = {c.name for c in figlio.commands}
        for nome, atteso in ATTESI.items():
            assert atteso <= trovati[nome], f"/owner {nome}: mancano {atteso - trovati[nome]}"
        assert len(owner.commands) <= 25
    finally:
        await bot.remove_cog("OwnerPremiumCog")


async def test_owner_non_e_nell_albero_globale_ma_solo_nel_server_dell_owner():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await owner_premium_setup(bot)
    try:
        assert bot.tree.get_command("owner") is None
        assert cg.registra_owner(bot.tree, 123) is True
        assert bot.tree.get_command("owner", guild=discord.Object(id=123)) is cg.GRUPPI["owner"]
        assert bot.tree.get_command("owner") is None
        # copy_global_to (sviluppo) non lo duplica
        guild = discord.Object(id=123)
        bot.tree.copy_global_to(guild=guild)
        assert [c.name for c in bot.tree.get_commands(guild=guild)].count("owner") == 1
    finally:
        await bot.remove_cog("OwnerPremiumCog")


async def test_chi_non_e_owner_viene_rifiutato_dal_gruppo(monkeypatch):
    import types

    import pytest

    from core import command_access as ca
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    monkeypatch.setattr(ca, "config", types.SimpleNamespace(OWNER_ID=1))
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await owner_premium_setup(bot)
    try:
        sottogruppo = cg.GRUPPI["owner"].get_command("premium")
        altro = fake_interaction(guild=fake_guild(guild_id=5), user=fake_member(user_id=2))
        with pytest.raises(ca.AccessoNegato):
            await sottogruppo.interaction_check(altro)
        lui = fake_interaction(guild=fake_guild(guild_id=5), user=fake_member(user_id=1))
        assert await sottogruppo.interaction_check(lui) is True
    finally:
        await bot.remove_cog("OwnerPremiumCog")
