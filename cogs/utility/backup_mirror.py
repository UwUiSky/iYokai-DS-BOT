"""
cogs/utility/backup_mirror.py
=================================
Listener che collega on_message al BackupMirrorDispatcher (SPEC.md
§11.9) — nessun comando qui, solo il ponte tra gli eventi di
discord.py e la logica testata in core/backup_mirror_dispatch.py.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.backup_mirror_dispatch import BackupMirrorDispatcher
from core.repositories.backup_mirror_repo import backup_mirror_repo


class BackupMirrorCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.dispatcher = BackupMirrorDispatcher(mirror_repo=backup_mirror_repo)

    def cog_unload(self) -> None:
        self.bot.loop.create_task(self.dispatcher.close())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await self.dispatcher.handle_message(message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackupMirrorCog(bot))
