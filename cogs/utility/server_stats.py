"""
cogs/utility/server_stats.py
================================
Server Stats (SPEC.md §14.18): un comando che mostra i numeri del
server (membri, canali, ruoli, boost) più un grafico di crescita
giornaliera basato sul log eventi unificato (core/repositories/
event_log_repo.py) — join/leave degli ultimi N giorni.
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.event_log_repo import event_log_repo
from core.server_stats_image import render_growth_chart
from core.server_stats_logic import compute_daily_net_change, fill_missing_days

MODULE_SERVER_STATS = "server_stats"
DEFAULT_DAYS = 14


class ServerStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="serverstats", description="Mostra le statistiche del server, con grafico di crescita."
    )
    @app_commands.describe(days="Quanti giorni indietro per il grafico (default 14, massimo 90)")
    async def server_stats(
        self,
        interaction: discord.Interaction,
        days: app_commands.Range[int, 1, 90] = DEFAULT_DAYS,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_SERVER_STATS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        since = datetime.now(timezone.utc) - timedelta(days=days)
        eventi_join = await event_log_repo.get_events_by_type_since(guild.id, "member_join", since)
        eventi_remove = await event_log_repo.get_events_by_type_since(
            guild.id, "member_remove", since
        )

        coppie = [(e.created_at, "member_join") for e in eventi_join] + [
            (e.created_at, "member_remove") for e in eventi_remove
        ]
        variazioni_grezze = compute_daily_net_change(coppie)
        variazioni = fill_missing_days(
            variazioni_grezze,
            start=since.date(),
            end=datetime.now(timezone.utc).date(),
        )

        immagine_bytes = await asyncio.to_thread(
            render_growth_chart, variazioni, f"Crescita membri — ultimi {days} giorni"
        )
        file = discord.File(io.BytesIO(immagine_bytes), filename="crescita.png")

        embed = discord.Embed(title=f"📊 Statistiche di {guild.name}", color=discord.Color.blurple())
        embed.add_field(name="Membri", value=str(guild.member_count), inline=True)
        embed.add_field(
            name="Canali",
            value=(
                f"{len(guild.text_channels)} testo\n"
                f"{len(guild.voice_channels)} vocali\n"
                f"{len(guild.categories)} categorie"
            ),
            inline=True,
        )
        embed.add_field(name="Ruoli", value=str(len(guild.roles)), inline=True)
        embed.add_field(
            name="Boost",
            value=f"Livello {guild.premium_tier} ({guild.premium_subscription_count} boost)",
            inline=True,
        )
        embed.add_field(
            name="Creato il",
            value=discord.utils.format_dt(guild.created_at, style="D"),
            inline=True,
        )
        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_image(url="attachment://crescita.png")

        await interaction.followup.send(embed=embed, file=file)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_SERVER_STATS,
            display_name="Server Stats",
            description="Statistiche del server con grafico di crescita giornaliera.",
            premium_capable=False,
        )
    )
    await bot.add_cog(ServerStatsCog(bot))
