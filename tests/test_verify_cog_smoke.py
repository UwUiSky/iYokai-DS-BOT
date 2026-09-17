"""
tests/test_verify_cog_smoke.py
=================================
Smoke test del cog Verify. Controlli standard ormai consolidati nel
progetto: view persistente, listener in bot.extra_events, comandi
registrati con i parametri attesi, istanziazione di CaptchaModal.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.security.verify import (
    MODULE_VERIFY,
    CaptchaModal,
    VerifyPanelView,
    setup as verify_setup,
)


async def test_verify_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await verify_setup(bot)

    assert bot.get_cog("VerifyCog") is not None

    module = registry.get(MODULE_VERIFY)
    assert module is not None
    assert module.premium_capable is False  # sempre gratis, come da schema

    verify_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "verify":
            verify_group = command
            break
    assert verify_group is not None

    sottocomandi = {c.name for c in verify_group.commands}
    assert {
        "setup",
        "panel",
        "whitelist-add",
        "whitelist-remove",
        "blacklist-add",
        "blacklist-remove",
    } <= sottocomandi

    setup_cmd = verify_group.get_command("setup")
    param_names = {p.name for p in setup_cmd.parameters}
    assert {
        "method",
        "verified_role",
        "min_account_age_days",
        "min_mutual_servers",
        "captcha_enabled",
        "log_channel",
    } <= param_names

    assert "on_raw_reaction_add" in bot.extra_events


def test_verify_panel_view_e_davvero_persistente():
    view = VerifyPanelView()
    assert view.is_persistent() is True
    assert view.timeout is None

    bottone = view.children[0]
    assert isinstance(bottone, discord.ui.Button)
    assert bottone.custom_id == "iyokai_verify_button"


def test_captcha_modal_si_istanzia_correttamente():
    # Nessuna dipendenza da Discord live: verifica solo che il Modal
    # dinamico (domanda generata a runtime, non dichiarata a livello
    # di classe come StaffReplyModal in spam_trap.py) si costruisca
    # senza eccezioni.
    modal = CaptchaModal(cog=None, guild_id=100, user_id=42)

    assert modal.title == "Verification"
    assert modal.guild_id == 100
    assert modal.user_id == 42
    assert len(modal.children) == 1
    assert isinstance(modal.children[0], discord.ui.Label)
    assert "What is" in modal.children[0].text
    # answer_input resta accessibile come attributo diretto (stesso
    # oggetto passato come component= al Label): è quello che
    # on_submit legge per il valore digitato dall'utente.
    assert isinstance(modal.answer_input, discord.ui.TextInput)
