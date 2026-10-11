"""
tests/test_f7_ticket_voice_gruppi.py
====================================
I comandi di ticket e vocali temporanei stanno in /ticket, /voice,
/gestione ticket e /gestione voice, col nome e il livello giusti
(mappa F7 passo 3b).
Funzioni coperte: NF-05 (issue #76)
"""

import discord
from discord import app_commands
from discord.ext import commands

from cogs.tickets.tickets import setup as tickets_setup
from cogs.voice_temp.voice_temp import setup as voice_setup
from core.command_access import Livello
from core.command_groups import GRUPPI
from tests.support.percorsi import percorsi_del_gruppo

TICKET_ATTESI = {"claim", "add", "remove", "rename", "priority", "close", "forceclose"}
GESTIONE_TICKET_ATTESI = {
    "ticket setup", "ticket panel", "ticket stats",
    "ticket categoria-add", "ticket categoria-remove", "ticket categoria-list",
    "ticket ruolo-add", "ticket ruolo-remove", "ticket ruolo-list",
}
VOICE_ATTESI = {"rename", "limit", "lock", "unlock", "kick", "transfer"}
GESTIONE_VOICE_ATTESI = {"voice setup", "voice panel", "voice cap", "voice piattaforme"}
VECCHI_TOP = {
    "ticket-setup", "ticket-panel", "ticket-stats", "ticket-category", "ticket-support-role",
    "voicetemp-setup", "voicetemp-panel", "voicetemp-cap", "voicetemp-platform-setup",
}


async def _bot():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await tickets_setup(bot)
    await voice_setup(bot)
    return bot


async def test_ticket_e_voice_stanno_nei_gruppi_giusti():
    bot = await _bot()
    try:
        assert TICKET_ATTESI <= percorsi_del_gruppo("ticket")
        assert VOICE_ATTESI <= percorsi_del_gruppo("voice")
        assert GESTIONE_TICKET_ATTESI <= percorsi_del_gruppo("gestione")
        assert GESTIONE_VOICE_ATTESI <= percorsi_del_gruppo("gestione")
        top = {c.name for c in bot.tree.get_commands()}
        assert not top & VECCHI_TOP
        assert {"ticket", "voice", "gestione"} <= top
    finally:
        for cog in list(bot.cogs):
            await bot.remove_cog(cog)


async def test_ticket_e_voice_aperti_a_tutti_gestione_solo_admin():
    assert GRUPPI["ticket"].livello is None
    assert GRUPPI["voice"].livello is None
    assert GRUPPI["gestione"].livello is Livello.ADMIN


async def test_un_solo_livello_di_sottogruppi_e_descrizioni_senza_prefisso():
    bot = await _bot()
    try:
        for nome in ("ticket", "voice", "gestione"):
            for figlio in GRUPPI[nome].commands:
                if isinstance(figlio, app_commands.Group):
                    assert not any(isinstance(n, app_commands.Group) for n in figlio.commands)
                assert not figlio.description.startswith("[")
    finally:
        for cog in list(bot.cogs):
            await bot.remove_cog(cog)
