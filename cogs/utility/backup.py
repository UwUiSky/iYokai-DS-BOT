"""
cogs/utility/backup.py
=========================
Comandi di orchestrazione Backup System (SPEC.md §11.12) — /define-
main e /define-backup, con i nomi esatti richiesti dallo schema
(non raggruppati sotto un prefisso comune). /restore-users NON è
qui: backup/restore utenti via OAuth2 (§11.10/§11.11) resta
deliberatamente rimandato — storage di credenziali OAuth altrui è un
tema di sicurezza da discutere con l'utente, non da presumere.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.repositories.backup_repo import backup_repo


class BackupCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="define-main", description="[Admin] Registra questo server come 'main' per il Backup System."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def define_main(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await backup_repo.define_main(guild.id)
        await interaction.response.send_message(
            "✅ Questo server è ora registrato come 'main' per il Backup System. "
            "Usa /define-backup per accodare la creazione di un backup.",
            ephemeral=True,
        )

    @app_commands.command(
        name="define-backup",
        description="[Admin] Accoda la creazione di un backup per questo server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def define_backup(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        coppia = await backup_repo.get_pair(guild.id)
        if coppia is None:
            await interaction.response.send_message(
                "Devi prima registrare questo server con /define-main.", ephemeral=True
            )
            return

        job_id = await backup_repo.enqueue_job(main_guild_id=guild.id)
        await interaction.response.send_message(
            f"📦 Backup accodato (job `#{job_id}`). Il processo può richiedere qualche minuto — "
            f"riceverai un DM con il link da cliccare per completare l'operazione quando è pronto.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackupCog(bot))
