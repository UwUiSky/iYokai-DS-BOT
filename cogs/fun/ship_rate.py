"""
cogs/fun/ship_rate.py
========================
Ship (SPEC.md §16.5) e Rate (§16.7). Deterministici via hash (core/
fun_logic.py) — stessa coppia o stesso testo danno sempre lo stesso
risultato, non un dado diverso ogni volta.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.fun_logic import (
    compute_rate_score,
    compute_ship_percentage,
    rate_flavor_text,
    ship_flavor_text,
)
from core.premium import PremiumModule, registry

MODULE_FUN = "fun"


def _barra_percentuale(percentuale: int, lunghezza: int = 10) -> str:
    piene = round(percentuale / 100 * lunghezza)
    return "█" * piene + "░" * (lunghezza - piene)


class ShipRateCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ship", description="Calcola la compatibilità tra due utenti.")
    @app_commands.describe(user1="Il primo utente", user2="Il secondo utente")
    async def ship(
        self,
        interaction: discord.Interaction,
        user1: discord.Member,
        user2: discord.Member,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_FUN):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return

        percentuale = compute_ship_percentage(user1.id, user2.id)
        embed = discord.Embed(
            title="💘 Ship",
            description=(
                f"**{user1.display_name}** + **{user2.display_name}**\n\n"
                f"{_barra_percentuale(percentuale)} **{percentuale}%**\n\n"
                f"{ship_flavor_text(percentuale)}"
            ),
            color=discord.Color.pink(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rate", description="Valuta qualcosa da 0 a 10.")
    @app_commands.describe(thing="Cosa vuoi far valutare")
    async def rate(self, interaction: discord.Interaction, thing: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_FUN):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return

        punteggio = compute_rate_score(thing)
        embed = discord.Embed(
            title="⭐ Rate",
            description=f"**{thing}**: {punteggio}/10\n\n{rate_flavor_text(punteggio)}",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_FUN,
            display_name="Fun",
            description="Comandi di intrattenimento (Ship, Rate).",
            premium_capable=False,
        )
    )
    await bot.add_cog(ShipRateCog(bot))
