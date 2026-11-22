"""
cogs/utility/backup_mirror.py
=================================
Listener che collega on_message al BackupMirrorDispatcher (SPEC.md
§11.9) — nessun comando qui, solo il ponte tra gli eventi di
discord.py e la logica testata in core/backup_mirror_dispatch.py.
Funzioni coperte: SPEC §11.9, BKP-028
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.backup_mirror_dispatch import BackupMirrorDispatcher
from core.repositories.backup_mirror_repo import backup_mirror_repo
from core.repositories.backup_sincronia_canali_repo import backup_sincronia_canali_repo


class BackupMirrorCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.dispatcher = BackupMirrorDispatcher(mirror_repo=backup_mirror_repo)
        # BKP-028: stessa coda ordinata, un invio alla volta; i messaggi di bot e webhook non tornano indietro.
        self.sincronia = BackupMirrorDispatcher(mirror_repo=backup_sincronia_canali_repo)

    async def cog_unload(self) -> None:
        # Attesa diretta: un task lanciato e non conservato può essere
        # eliminato da Python prima di chiudere la sessione HTTP.
        await self.dispatcher.close()
        await self.sincronia.close()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await self.dispatcher.handle_message(message)
        await self.sincronia.handle_message(message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackupMirrorCog(bot))
