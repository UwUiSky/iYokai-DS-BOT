"""
cogs/user_app/voce_app.py
=========================
Menu «Trascrivi vocale» di iYokai App (tasto destro su un messaggio vocale): testo del vocale e traduzione nella
lingua del client, solo per chi preme. Spento finché manca un servizio di trascrizione che non addestra (D19).
Funzioni coperte: SPEC §25.104 (AI-R-111)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai.voce import trascrivi_e_traduci
from core.user_app_bot import e_istanza_app

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)


class VoceAppCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._menu = app_commands.ContextMenu(
            name="Trascrivi vocale", callback=self.menu_trascrivi, allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE
        )
        bot.tree.add_command(self._menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self._menu.name, type=self._menu.type)

    async def menu_trascrivi(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        await trascrivi_e_traduci(interaction, messaggio)


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app."""
    if e_istanza_app(bot):
        await bot.add_cog(VoceAppCog(bot))
