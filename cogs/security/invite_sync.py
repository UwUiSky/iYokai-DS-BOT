"""
cogs/security/invite_sync.py
===============================
Il collegamento tra la classe di servizio InviteTracker
(core/invite_tracker.py) e gli eventi Discord reali. Vive sotto
cogs/ (non in core/) perché core/cog_manager.py scopre e carica
automaticamente solo i moduli dentro il pacchetto `cogs` — vedi la
nota in cima a core/invite_tracker.py per il ragionamento completo.

Non è un modulo attivabile/disattivabile per server: la cache degli
inviti serve silenziosamente in background a qualunque altro modulo
la interroghi (Spam Trap oggi, Verify in futuro) — non ha comandi
propri, non si registra nel PremiumRegistry.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from core.invite_tracker import invite_tracker


class InviteSyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await invite_tracker.refresh_guild(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await invite_tracker.refresh_guild(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is not None:
            await invite_tracker.refresh_guild(invite.guild)  # type: ignore[arg-type]

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is not None:
            await invite_tracker.refresh_guild(invite.guild)  # type: ignore[arg-type]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InviteSyncCog(bot))
