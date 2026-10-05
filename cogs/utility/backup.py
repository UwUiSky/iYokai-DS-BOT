"""
cogs/utility/backup.py
======================
Comandi /define-main, /define-backup e /promuovi-backup del Backup System.
/restore-users è in cogs/utility/restore.py.
Funzioni coperte: SPEC §11.12, §11.13
"""

# DA FARE (issue #68, fase F3): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §12 (Backup e restore).
# DA FARE (issue #110, fase F13): NF-39, Modelli di server e sincronia
#   tra server. Vedi revisione/02-piano/NUOVE_FUNZIONI.md.

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

        if await backup_repo.has_active_job(guild.id):
            await interaction.response.send_message(
                "⏳ C'è già un backup in coda o in corso per questo server: "
                "attendi che finisca prima di accodarne un altro.",
                ephemeral=True,
            )
            return

        job_id = await backup_repo.enqueue_job(main_guild_id=guild.id)
        await interaction.response.send_message(
            f"📦 Backup accodato (job `#{job_id}`). Il processo può richiedere qualche minuto — "
            f"riceverai un DM con il link da cliccare per completare l'operazione quando è pronto.",
            ephemeral=True,
        )

    @app_commands.command(
        name="promuovi-backup",
        description="[Admin] Promuove QUESTO server (finora backup) a nuovo main, se il main originale è perso.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def promuovi_backup(self, interaction: discord.Interaction) -> None:
        """
        SPEC.md §11.13 — auto-propagazione: quando un server backup
        viene promosso a main, accoda IMMEDIATAMENTE la creazione di
        un nuovo backup per lui, così non resta mai "main senza
        backup" più del tempo strettamente necessario a rimetterlo
        in coda.

        Va lanciato DENTRO al server che finora era il backup — non
        serve altro ID: lo troviamo risalendo da backup_guild_id a
        chi era il suo main tramite get_pair_by_backup_guild_id.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        coppia = await backup_repo.get_pair_by_backup_guild_id(guild.id)
        if coppia is None:
            await interaction.response.send_message(
                "⚠️ Questo server non risulta registrato come backup di nessun main — "
                "non c'è nulla da promuovere.",
                ephemeral=True,
            )
            return

        await backup_repo.promote_backup_to_main(
            old_main_guild_id=coppia.main_guild_id, new_main_guild_id=guild.id
        )
        job_id = await backup_repo.enqueue_job(main_guild_id=guild.id)

        await interaction.response.send_message(
            "👑 Questo server è stato promosso a **main**. Il vecchio main "
            f"(`{coppia.main_guild_id}`) non è più abbinato a questo backup. "
            f"Un nuovo backup per QUESTO server è già stato accodato automaticamente "
            f"(job `#{job_id}`) — riceverai un DM con il link quando è pronto.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackupCog(bot))
