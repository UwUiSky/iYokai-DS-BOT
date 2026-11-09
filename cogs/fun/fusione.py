"""
cogs/fun/fusione.py
===================
`/immagini fusione a: b:`: due Pokémon, il nome fuso e le loro immagini ufficiali affiancate (nessuna fusione
disegnata: vedi D18 in `core/fusione_logic.py`). Pillow fuori dal ciclo principale, pausa per utente.
Funzioni coperte: SPEC §16 (FUN-057; B11 di #131)
Dipende da: core/fusione_logic.py, core/schede_giochi_logic.py
"""

from __future__ import annotations

import io
import time

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.entertainment import MODULE_FUN
from core import fusione_logic as fl
from core import schede_giochi_logic as sl
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import lingua_interazione, testo_per
from core.repositories.cache_esterna_repo import cache_esterna_repo

PAUSA_SECONDI = 10
MAX_UTENTI_NELLA_PAUSA = 500


class FusioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._ultima: dict[int, float] = {}

    def _pausa(self, utente_id: int) -> int:
        ora = time.monotonic()
        resta = PAUSA_SECONDI - (ora - self._ultima.get(utente_id, -1e9))
        if resta > 0:
            return int(resta) + 1
        if len(self._ultima) >= MAX_UTENTI_NELLA_PAUSA:
            self._ultima = {u: t for u, t in self._ultima.items() if ora - t < PAUSA_SECONDI}
        self._ultima[utente_id] = ora
        return 0

    @comando_di_gruppo("immagini", nome="fusione", descrizione="Due Pokémon: il nome fuso e le loro immagini ufficiali affiancate.")
    @app_commands.describe(a="Il primo Pokémon", b="Il secondo Pokémon")
    async def fusione(
        self, interaction: discord.Interaction, a: app_commands.Range[str, 1, sl.MAX_NOME], b: app_commands.Range[str, 1, sl.MAX_NOME]
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return
        resta = self._pausa(interaction.user.id)
        if resta:
            await interaction.response.send_message(await testo_per(interaction, "immagini_post_aspetta", secondi=resta), ephemeral=True)
            return
        await interaction.response.defer()
        esito = await fl.fondi(a, b, await lingua_interazione(interaction, pubblica=True), cache_esterna_repo)
        if esito is None:
            await interaction.delete_original_response()
            await interaction.followup.send(await testo_per(interaction, "fusione_non_trovata"), ephemeral=True)
            return
        nome, png = esito
        embed = discord.Embed(title=nome[:256], description=(await testo_per(interaction, "fusione_descrizione", pubblica=True, a=a[:100], b=b[:100]))[:4000],
                              color=discord.Color.orange())
        embed.set_image(url="attachment://fusione.png")
        embed.set_footer(text=(await testo_per(interaction, "fusione_credito", pubblica=True))[:2048])
        await interaction.followup.send(embed=embed, file=discord.File(io.BytesIO(png), filename="fusione.png"),
                                        allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FusioneCog(bot))
