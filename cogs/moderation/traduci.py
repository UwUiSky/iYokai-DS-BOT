"""
cogs/moderation/traduci.py
==========================
Registra il bottone persistente «Traduci» dei messaggi pubblici di moderazione, cosi' continua a rispondere
dopo un riavvio. La logica sta in core/moderazione_traduci.py.
Funzioni coperte: SPEC §5.13 (#115, D110)
"""

from __future__ import annotations

from discord.ext import commands

from core.moderazione_traduci import VistaTraduci


class TraduciCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(VistaTraduci())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TraduciCog(bot))
