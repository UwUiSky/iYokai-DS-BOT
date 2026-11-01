"""
cogs/moderation/rischio_staff.py
================================
/mod rischio: il punteggio di rischio di un membro (casi, trappola anti-spam, età dell'account,
doppi della verifica web). /mod carico: quanto lavoro ha fatto ogni persona dello staff.
Servono a chi decide: nessuna azione parte da qui. Risposte private.
Funzioni coperte: SPEC §23.17 (NF-41, D50)
Dipende da: core/staff_rischio_logic.py, core/repositories/staff_carico_repo.py
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import MODULE_CASE_SYSTEM, ensure_module_enabled
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.premium import requires_module
from core.repositories.staff_carico_repo import staff_carico_repo
from core.staff_rischio_logic import SegnaliRischio, calcola_rischio, testo_carico, testo_rischio

GIORNI_CARICO_MAX = 90


def _giorni_da(quando: datetime | None) -> int | None:
    if quando is None:
        return None
    return max(0, (datetime.now(timezone.utc) - quando).days)


class RischioStaffCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "mod",
        nome="rischio",
        descrizione="Punteggio di rischio di un membro, con i motivi. Solo un aiuto per decidere.",
    )
    @app_commands.describe(member="Il membro da valutare")
    @requires_module(MODULE_CASE_SYSTEM)
    async def rischio(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        guild = interaction.guild
        warn, timeout, kick, ban, trappola = await staff_carico_repo.segnali_utente(guild.id, member.id)
        segnali = SegnaliRischio(
            warn_attivi=warn,
            timeout_90_giorni=timeout,
            kick=kick,
            ban_o_tempban=ban,
            spam_trap=trappola,
            eta_account_giorni=_giorni_da(member.created_at),
            giorni_nel_server=_giorni_da(member.joined_at),
            doppi=tuple(await staff_carico_repo.doppi_di(guild.id, member.id)),
        )
        embed = discord.Embed(
            title=f"Rischio — {member.display_name}"[:256],
            description=testo_rischio(calcola_rischio(segnali)),
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "mod",
        nome="carico",
        descrizione="Quanto lavoro ha fatto ogni persona dello staff (casi, appelli, ticket).",
    )
    @app_commands.describe(giorni=f"Quanti giorni guardare, da 1 a {GIORNI_CARICO_MAX} (di base 30)")
    @requires_module(MODULE_CASE_SYSTEM)
    async def carico(
        self, interaction: discord.Interaction, giorni: app_commands.Range[int, 1, GIORNI_CARICO_MAX] = 30
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        escludi = (self.bot.user.id,) if self.bot.user is not None else ()
        righe = await staff_carico_repo.carico(interaction.guild.id, giorni, escludi)
        embed = discord.Embed(
            title="Carico dello staff", description=testo_carico(righe, giorni)[:4000], color=discord.Color.blurple()
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RischioStaffCog(bot))
