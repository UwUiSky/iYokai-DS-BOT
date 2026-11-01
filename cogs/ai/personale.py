"""
cogs/ai/personale.py
====================
Comandi della persona dentro `/assistente`: assistente acceso o spento per sé.
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

    @comando_di_gruppo("assistente", nome="preferenza", descrizione="Le tue scelte sull'AI: risposte per te e stile imitabile dagli altri.")
    @app_commands.describe(
        acceso="Sì: l'assistente ti risponde. No: per te resta spento",
        stile="Sì: gli altri possono chiedere un messaggio scritto nel tuo stile (di partenza no)",
    )
    async def preferenza(self, interaction: discord.Interaction, acceso: bool | None = None, stile: bool | None = None) -> None:
        if acceso is None and stile is None:
            await interaction.response.send_message("Indica almeno una scelta.", ephemeral=True)
            return
        righe = []
        if acceso is not None:
            await ai_repo.imposta_assistente(interaction.user.id, acceso)
            servizio_ai().dimentica_preferenza(interaction.user.id)
            righe.append("Assistente acceso per te." if acceso else "Assistente spento per te: non ti risponderà più. Vale in ogni server.")
        if stile is not None:
            await ai_repo.imposta_stile_consentito(interaction.user.id, stile)
            righe.append(
                "Gli altri possono chiedere un messaggio nel tuo stile: l'AI legge tuoi messaggi recenti del canale. Puoi toglierlo quando vuoi."
                if stile else "Nessuno può chiedere un messaggio nel tuo stile."
            )
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiPersonaleCog(bot))
