"""
cogs/security/invite_sync.py
===============================
Il collegamento tra la classe di servizio InviteTracker
(core/invite_tracker.py) e gli eventi Discord reali. Vive sotto
cogs/ (non in core/) perché core/cog_manager.py scopre e carica
automaticamente solo i moduli dentro il pacchetto `cogs` — vedi la
nota in cima a core/invite_tracker.py per il ragionamento completo.

Non ha comandi propri e non si registra nel PremiumRegistry: tiene
aggiornata la cache degli inviti per i moduli che la usano (Spam Trap
e log avanzati). Gli inviti si leggono solo nei server dove almeno uno
di quei moduli è attivo: leggerli ovunque costava una chiamata a
Discord per ogni server a ogni avvio.
"""

# DA FARE (issue #59, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §3 (Sicurezza (anti-raid,
#   anti-nuke, spam-trap, ban globale)).

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from core.database import db
from core.invite_tracker import invite_tracker

logger = logging.getLogger("iyokai.invite_sync")

# I moduli che chiedono "con quale invito è entrato questo membro?".
# Chi ne aggiunge uno nuovo lo scrive qui.
MODULI_CHE_USANO_GLI_INVITI = ("spam_trap", "logging_advanced")


async def inviti_servono(guild_id: int) -> bool:
    """True se in questo server almeno un modulo usa la cache degli inviti."""
    for nome_modulo in MODULI_CHE_USANO_GLI_INVITI:
        if await db.is_module_active_for_guild(guild_id, nome_modulo):
            return True
    return False


class InviteSyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _aggiorna_se_serve(self, guild: discord.Guild) -> None:
        if await inviti_servono(guild.id):
            await invite_tracker.refresh_guild(guild)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in list(self.bot.guilds):
            try:
                await self._aggiorna_se_serve(guild)
            except Exception:
                # Un server che dà errore non ferma il giro per gli altri.
                logger.exception("Errore leggendo gli inviti del server %s", guild.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._aggiorna_se_serve(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is not None:
            await self._aggiorna_se_serve(invite.guild)  # type: ignore[arg-type]

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is not None:
            await self._aggiorna_se_serve(invite.guild)  # type: ignore[arg-type]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InviteSyncCog(bot))
