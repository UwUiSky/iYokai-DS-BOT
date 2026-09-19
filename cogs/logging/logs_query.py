"""
cogs/logging/logs_query.py
=============================
Interfaccia comandi sul log eventi unificato (BACKLOG.md §3):
/logs user, /logs channel, /logs export. Nessuna logica propria
oltre alla formattazione — legge tramite core/repositories/
event_log_repo.py, scritto da cogs/logging/basic_logs.py.

Nessun gate is_module_active_for_guild qui: se il modulo è
disattivato, semplicemente non c'è nulla da mostrare (la tabella
resta vuota per quel server) — non serve bloccare il comando stesso,
che a differenza dei listener non ha nessun costo continuo.
"""

from __future__ import annotations

import io
import json

import discord
from discord import app_commands
from discord.ext import commands

from core.repositories.event_log_repo import EventLogEntry, event_log_repo


def _format_entry(entry: EventLogEntry) -> str:
    quando = discord.utils.format_dt(entry.created_at, style="R")
    pezzi = [f"`#{entry.id}` **{entry.event_type}** — {quando}"]
    if entry.actor_id:
        pezzi.append(f"da <@{entry.actor_id}>")
    if entry.case_number:
        pezzi.append(f"(caso #{entry.case_number})")
    if entry.details:
        pezzi.append(f"`{json.dumps(entry.details, ensure_ascii=False)}`")
    return " ".join(pezzi)


class LogsQueryCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    logs_group = app_commands.Group(
        name="logs", description="Consulta lo storico eventi del server."
    )

    @logs_group.command(name="user", description="[Admin] Mostra lo storico eventi di un utente.")
    @app_commands.describe(
        member="L'utente da consultare", limit="Quante voci mostrare (default 15, massimo 25)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_user(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        limit: app_commands.Range[int, 1, 25] = 15,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        eventi = await event_log_repo.get_events_by_user(guild.id, member.id, limit=limit)
        if not eventi:
            await interaction.response.send_message(
                f"Nessun evento registrato per {member.mention}.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📜 Storico eventi — {member}",
            description="\n".join(_format_entry(e) for e in eventi),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @logs_group.command(
        name="channel", description="[Admin] Mostra lo storico eventi di un canale."
    )
    @app_commands.describe(
        channel="Il canale da consultare", limit="Quante voci mostrare (default 15, massimo 25)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        limit: app_commands.Range[int, 1, 25] = 15,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        eventi = await event_log_repo.get_events_by_channel(guild.id, channel.id, limit=limit)
        if not eventi:
            await interaction.response.send_message(
                f"Nessun evento registrato per {channel.mention}.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📜 Storico eventi — #{channel.name}",
            description="\n".join(_format_entry(e) for e in eventi),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @logs_group.command(
        name="export",
        description="[Admin] Esporta lo storico eventi completo del server come file JSON.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_export(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        eventi = await event_log_repo.export_events(guild.id)
        payload = [
            {
                "id": e.id,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "target_user_id": e.target_user_id,
                "channel_id": e.channel_id,
                "role_id": e.role_id,
                "case_number": e.case_number,
                "details": e.details,
                "created_at": e.created_at.isoformat(),
            }
            for e in eventi
        ]
        contenuto = json.dumps(payload, ensure_ascii=False, indent=2)
        file_bytes = io.BytesIO(contenuto.encode("utf-8"))
        file = discord.File(file_bytes, filename=f"event_log_{guild.id}.json")

        await interaction.followup.send(
            f"Export completo: {len(eventi)} eventi.", file=file, ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogsQueryCog(bot))
