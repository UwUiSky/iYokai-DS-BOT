"""
cogs/utility/invites.py
=======================
Inviti (NF-27, SPEC §23): ogni ingresso viene attribuito all'invito usato (via
core/invite_tracker.resolve_join_invite) e si può vedere quante persone ha invitato un
membro e la classifica del server (10 righe). L'attribuzione è "giusta o sconosciuta", ma
con ingressi simultanei o vanity URL può mancare: lo diciamo sempre (LC-6).
Comandi: `/level inviti utente|classifica`.
Funzioni coperte: SPEC §23 (NF-27)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.invite_tracker import invite_tracker
from core.premium import PremiumModule, registry
from core.repositories.invite_stats_repo import invite_stats_repo

logger = logging.getLogger("iyokai.invites")

MODULE_INVITES = "invites"
_SG_INVITI = ("inviti", "Quante persone ha invitato ognuno")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
AVVISO_ATTRIBUZIONE = (
    "Nota: l'invito usato si riconosce con buona affidabilità, non al 100%. "
    "Con ingressi simultanei o con il link personalizzato del server l'ingresso può non essere attribuito."
)


class InvitesCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot or not await db.is_module_active_for_guild(member.guild.id, MODULE_INVITES):
            return
        try:
            trovato = await invite_tracker.resolve_join_invite(member.guild, member.id)
            if trovato is None or trovato[1] is None or trovato[1] == member.id:
                return
            await invite_stats_repo.record_join(member.guild.id, member.id, trovato[1], trovato[0])
        except Exception:
            logger.exception("Errore nel registrare l'invito di %s", member.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        invite_tracker.forget_member(member.guild.id, member.id)
        if member.bot:
            return
        try:
            await invite_stats_repo.mark_left(member.guild.id, member.id)
        except Exception:
            logger.exception("Errore nel segnare l'uscita di %s", member.id)

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_INVITES):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo("level", nome="utente", descrizione="Quante persone ha invitato un membro.", sottogruppo=_SG_INVITI)
    @app_commands.describe(utente="Il membro (se vuoto, tu)")
    async def utente(self, interaction: discord.Interaction, utente: discord.Member | None = None) -> None:
        if not await self._pronto(interaction):
            return
        bersaglio = utente or interaction.user
        s = await invite_stats_repo.stats_for(interaction.guild.id, bersaglio.id)
        await interaction.response.send_message(
            f"{bersaglio.mention} ha invitato {s.totale} persone: {s.presenti} sono ancora nel server, "
            f"{s.totale - s.presenti} sono uscite.\n{AVVISO_ATTRIBUZIONE}",
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("level", nome="classifica", descrizione="I 10 membri che hanno invitato più persone.", sottogruppo=_SG_INVITI)
    async def classifica(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        righe = await invite_stats_repo.top(interaction.guild.id)
        if not righe:
            await interaction.response.send_message(
                f"Nessun invito registrato finora.\n{AVVISO_ATTRIBUZIONE}", ephemeral=True
            )
            return
        testo = "\n".join(
            f"{i}. <@{uid}>: {s.presenti} presenti ({s.totale} in tutto)" for i, (uid, s) in enumerate(righe, 1)
        )
        await interaction.response.send_message(
            f"**Classifica inviti**\n{testo}\n{AVVISO_ATTRIBUZIONE}",
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_INVITES,
            display_name="Inviti",
            category="utility",
            description="Chi ha invitato chi e classifica degli inviti.",
            premium_capable=False,
        )
    )
    await bot.add_cog(InvitesCog(bot))
