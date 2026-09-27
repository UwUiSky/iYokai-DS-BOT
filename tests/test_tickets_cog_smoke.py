"""
tests/test_tickets_cog_smoke.py
==================================
Smoke test del sistema di ticket. Il controllo più importante è che
TicketPanelView sia davvero PERSISTENTE (timeout=None + custom_id
esplicito): se setup() non sollevasse eccezioni sarebbe già un buon
segno (bot.add_view() rifiuta con ValueError una view non
persistente), ma qui lo verifichiamo anche esplicitamente con
view.is_persistent(), così un domani se qualcuno rimuove il
custom_id o aggiunge un timeout per errore, il test lo segnala
chiaramente invece di un generico "setup ha sollevato un'eccezione".
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.tickets.tickets import MODULE_TICKETS, TicketPanelView, setup as tickets_setup


async def test_tickets_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await tickets_setup(bot)

    assert bot.get_cog("TicketsCog") is not None

    module = registry.get(MODULE_TICKETS)
    assert module is not None
    assert module.premium_capable is False

    comandi = {c.name for c in bot.tree.get_commands()}
    assert {
        "ticket-setup",
        "ticket-panel",
        "ticket-category",
        "ticket-support-role",
        "ticket-stats",
    } <= comandi

    gruppi = {c.name: c for c in bot.tree.get_commands() if isinstance(c, app_commands.Group)}

    ticket_group = gruppi["ticket"]
    sottocomandi = {c.name for c in ticket_group.commands}
    assert {"claim", "add", "remove", "rename", "priority", "close", "forceclose"} <= sottocomandi

    categoria_group = gruppi["ticket-category"]
    assert {c.name for c in categoria_group.commands} == {"add", "remove", "list"}

    supporto_group = gruppi["ticket-support-role"]
    assert {c.name for c in supporto_group.commands} == {"add", "remove", "list"}

    assert "on_message" in bot.extra_events


def test_ticket_panel_view_e_davvero_persistente():
    view = TicketPanelView()
    assert view.is_persistent() is True
    assert view.timeout is None

    bottone = view.children[0]
    assert isinstance(bottone, discord.ui.Button)
    assert bottone.custom_id == "iyokai_ticket_open"
