"""
cogs/fun/giochi_extra.py
========================
Giochi piccoli del gruppo /giochi (#131, D70): `/giochi minato` (campo minato con gli spoiler).
Nessuna puntata e nessuna moneta: i giochi di fortuna non si monetizzano.
Funzioni coperte: SPEC §16 (FUN-009)
Dipende da: core/fun_piccoli_logic.py
"""

from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.entertainment import MODULE_FUN
from core import fun_piccoli_logic as piccoli
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per

NESSUNA_MENZIONE = discord.AllowedMentions.none()


class GiochiExtraCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()

    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True
            )
            return False
        return True

    @comando_di_gruppo("giochi", nome="minato", descrizione="Campo minato: tocca gli spoiler ed evita le mine.")
    @app_commands.describe(difficolta="Quanto è grande il campo (di base: facile)")
    @app_commands.choices(
        difficolta=[
            app_commands.Choice(name="Facile (5x5)", value="facile"),
            app_commands.Choice(name="Medio (7x7)", value="medio"),
            app_commands.Choice(name="Difficile (9x9)", value="difficile"),
        ]
    )
    async def minato(
        self, interaction: discord.Interaction, difficolta: app_commands.Choice[str] | None = None
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        livello = difficolta.value if difficolta is not None else "facile"
        campo = piccoli.crea_minato(livello, self._rng)
        mine = piccoli.MINATO_LIVELLI[livello][1]
        intestazione = await testo_per(interaction, "fun_minato_intro", pubblica=True, mine=mine)
        await interaction.response.send_message(
            f"{intestazione}\n{piccoli.testo_minato(campo)}"[: piccoli.MAX_MESSAGGIO],
            allowed_mentions=NESSUNA_MENZIONE,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiochiExtraCog(bot))
