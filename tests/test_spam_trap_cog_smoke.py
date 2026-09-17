"""
tests/test_spam_trap_cog_smoke.py
=====================================
Smoke test del cog Spam Trap. Oltre al solito controllo di
caricamento, verifica esplicitamente che le classi UI più delicate
del file (AppealActionsView, StaffReplyModal — mai usate prima nel
progetto: Modal con title come class kwarg, TextInput dichiarato a
livello di classe) si istanzino davvero senza sollevare eccezioni.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.security.spam_trap import (
    MODULE_SPAM_TRAP,
    AppealActionsView,
    StaffReplyModal,
    setup as spam_trap_setup,
)


async def test_spam_trap_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await spam_trap_setup(bot)

    assert bot.get_cog("SpamTrapCog") is not None

    module = registry.get(MODULE_SPAM_TRAP)
    assert module is not None
    assert module.premium_capable is True  # candidato premium, come da schema

    comandi = {c.name for c in bot.tree.get_commands()}
    assert "spamtrap-setup" in comandi

    setup_cmd = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Command) and command.name == "spamtrap-setup":
            setup_cmd = command
            break
    assert setup_cmd is not None
    param_names = {p.name for p in setup_cmd.parameters}
    assert {"trap_channel", "log_channel"} <= param_names

    # I due listener: on_message (indicizzazione + trigger + appeal
    # via DM) e on_member_join (cattura invito al join).
    assert {"on_message", "on_member_join"} <= set(bot.extra_events.keys())


def test_appeal_actions_view_si_istanzia_correttamente():
    view = AppealActionsView(guild_id=100, case_number=1, user_id=42)

    assert view.guild_id == 100
    assert view.case_number == 1
    assert view.user_id == 42

    bottoni = [c for c in view.children if isinstance(c, discord.ui.Button)]
    etichette = {b.label for b in bottoni}
    assert {"Unban", "Reject", "Reply"} <= etichette


def test_staff_reply_modal_si_istanzia_correttamente():
    # Punto delicato verificato esplicitamente: Modal con title come
    # class kwarg + TextInput dichiarato a livello di classe — mai
    # usato prima in questo progetto, verificato con inspect prima
    # di scrivere il file (vedi sessione di sviluppo), qui riverificato
    # nel contesto reale del modulo.
    modal = StaffReplyModal(user_id=42)

    assert modal.title == "Reply to user"
    assert modal.user_id == 42
    assert len(modal.children) == 1
    assert isinstance(modal.children[0], discord.ui.TextInput)
