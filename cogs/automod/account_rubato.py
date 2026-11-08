"""
cogs/automod/account_rubato.py
==============================
Ascolta i messaggi dei server e passa a core/account_rubato.py quelli che servono a riconoscere un account
rubato (D67): lo stesso messaggio o inoltro in più canali o server in poco tempo. Le immagini malevole le
segnala il filtro immagini (cogs/automod/immagini.py) allo stesso modulo.
Funzioni coperte: SPEC §6.20 (D67, #153)
Dipende da: core/account_rubato.py
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from core import account_rubato

logger = logging.getLogger("iyokai.account_rubato")


class AccountRubatoCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        try:
            await account_rubato.controlla_messaggio(self.bot, message)
        except Exception:
            logger.exception("Account rubato: errore imprevisto")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AccountRubatoCog(bot))
