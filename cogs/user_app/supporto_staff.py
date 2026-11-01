"""
cogs/user_app/supporto_staff.py
===============================
Lato staff dell'assistenza di iYokai App (SPEC §B.9), sul bot principale: un messaggio scritto in un thread
del canale `SUPPORT_CHANNEL_ID` va in DM a chi ha aperto la richiesta; archiviare il thread chiude la richiesta.
Non ha comandi.
Funzioni coperte: SPEC §B.9 (NF-36, #107)
Dipende da: core/support_service.py
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from core.config import config
from core.support_service import chiudi_se_archiviato, inoltra_risposta_staff

logger = logging.getLogger("iyokai.support")


class SupportoStaffCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        canale = message.channel
        if not config.SUPPORT_CHANNEL_ID or getattr(canale, "parent_id", None) != config.SUPPORT_CHANNEL_ID:
            return
        try:
            await inoltra_risposta_staff(self.bot, message)
        except Exception:  # noqa: BLE001 - un errore nel database non deve fermare gli altri ascoltatori
            logger.warning("Risposta dello staff non inoltrata.", exc_info=True)

    @commands.Cog.listener()
    async def on_thread_update(self, prima: discord.Thread, dopo: discord.Thread) -> None:
        if not config.SUPPORT_CHANNEL_ID or dopo.parent_id != config.SUPPORT_CHANNEL_ID:
            return
        if dopo.archived and not prima.archived:
            try:
                await chiudi_se_archiviato(self.bot, dopo)
            except Exception:  # noqa: BLE001
                logger.warning("Richiesta di assistenza non chiusa.", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    """Solo sul bot principale: gli altri client (app, NSFW, musica) non ascoltano i thread dello staff."""
    if getattr(bot, "istanza", None) is None:
        await bot.add_cog(SupportoStaffCog(bot))
