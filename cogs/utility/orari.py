"""
cogs/utility/orari.py
=====================
Menu del tasto destro «Orari nel mio fuso»: trova gli orari scritti in un messaggio (18:30, 6pm) e li
riscrive come timestamp di Discord, che ognuno vede nel proprio fuso. Usa il fuso salvato da chi ha scritto
il messaggio (`/utility lingua fuso:`), altrimenti quello del server (Europe/Rome).
Funzioni coperte: catalogo #128 UTL-104 (D69, B6)
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.i18n import lingua_interazione, t
from core.orari_logic import fuso_da_nome, righe_orari
from core.programmati_logic import FUSO_PREDEFINITO
from core.repositories.utente_fuso_repo import utente_fuso_repo

NOME_MENU = "Orari nel mio fuso"


class OrariCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._menu = app_commands.ContextMenu(name=NOME_MENU, callback=self.menu_orari)

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self._menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(NOME_MENU, type=discord.AppCommandType.message)

    async def menu_orari(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        lingua = await lingua_interazione(interaction)
        nome_fuso = await utente_fuso_repo.get(messaggio.author.id)
        righe = righe_orari(messaggio.content or "", fuso_da_nome(nome_fuso, FUSO_PREDEFINITO), datetime.now(timezone.utc))
        if not righe:
            await interaction.response.send_message(t("orari_nessuno", lingua), ephemeral=True)
            return
        testo = t("orari_titolo", lingua, fuso=nome_fuso or FUSO_PREDEFINITO) + "\n" + "\n".join(righe)
        await interaction.response.send_message(testo[:2000], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrariCog(bot))
