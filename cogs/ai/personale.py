"""
cogs/ai/personale.py
====================
Comandi della persona dentro `/utility ai`: assistente acceso o spento per sé.
Funzioni coperte: SPEC §25.87 (AI-R-094)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import SOTTO_AI, registra_modulo_ai
from core.ai_servizio import servizio_ai
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.repositories.ai_repo import ai_repo


class AiPersonaleCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("utility", nome="preferenza", descrizione="Accendi o spegni per te le risposte dell'AI.", sottogruppo=SOTTO_AI)
    @app_commands.describe(acceso="Sì: l'assistente ti risponde. No: per te resta spento")
    async def preferenza(self, interaction: discord.Interaction, acceso: bool) -> None:
        await ai_repo.imposta_assistente(interaction.user.id, acceso)
        servizio_ai().dimentica_preferenza(interaction.user.id)
        testo = "Assistente acceso per te." if acceso else "Assistente spento per te: non ti risponderà più. Vale in ogni server."
        await interaction.response.send_message(testo, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiPersonaleCog(bot))
