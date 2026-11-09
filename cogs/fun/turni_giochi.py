"""
cogs/fun/turni_giochi.py
========================
`/web turni gioco:` (#131, D70, B11): le rotazioni di Splatoon 3 e i reset settimanali di World of Warcraft.
Sottocomando di `/web` registrato da questo cog (come `/web scheda`). I tempi sono orari di Discord.
Funzioni coperte: SPEC §16 (FUN-071)
Dipende da: core/turni_logic.py, core/repositories/cache_esterna_repo.py
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core import turni_logic as tl
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_interazione, t
from core.repositories.cache_esterna_repo import cache_esterna_repo

NOMI_MODI = {"regular": "turni_modo_regular", "serie": "turni_modo_serie", "open": "turni_modo_open", "x": "turni_modo_x"}


def _quando(turno: dict) -> str:
    return f"<t:{turno['inizio']}:t> - <t:{turno['fine']}:t> (<t:{turno['inizio']}:R>)"


def embed_splatoon(dati: dict, lingua: str) -> discord.Embed:
    embed = discord.Embed(title=t("turni_titolo_splatoon3", lingua), color=discord.Color.orange())
    for modo in dati["modi"]:
        righe = [f"{_quando(x)}\n**{x['regola']}** · {' / '.join(x['mappe'])}" for x in modo["turni"]]
        embed.add_field(name=t(NOMI_MODI[modo["id"]], lingua)[:256], value="\n".join(righe)[:1024], inline=False)
    if dati["salmon"]:
        righe = []
        for s in dati["salmon"]:
            armi = f"\n{', '.join(s['armi'])}" if s["armi"] else ""
            righe.append(f"<t:{s['inizio']}:d> - <t:{s['fine']}:d>\n**{s['mappa']}**{' · ' + s['boss'] if s['boss'] else ''}{armi}")
        embed.add_field(name=t("turni_modo_salmon", lingua), value="\n".join(righe)[:1024], inline=False)
    embed.set_footer(text=t("turni_fonte_splatoon3", lingua)[:2048])
    return embed


def embed_wow(adesso: datetime, lingua: str) -> discord.Embed:
    reset = tl.reset_wow(adesso)
    corpo = t("turni_wow_corpo", lingua, us=f"<t:{reset['us']}:F> (<t:{reset['us']}:R>)", eu=f"<t:{reset['eu']}:F> (<t:{reset['eu']}:R>)")
    embed = discord.Embed(title=t("turni_titolo_wow", lingua), description=corpo[:4000], color=discord.Color.dark_gold())
    embed.set_footer(text=t("turni_fonte_wow", lingua)[:2048])
    return embed


class TurniGiochiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("web", nome="turni", descrizione="Le rotazioni di Splatoon 3 e il reset settimanale di World of Warcraft.")
    @app_commands.describe(gioco="Di quale gioco")
    @app_commands.choices(
        gioco=[
            app_commands.Choice(name="Splatoon 3: mappe e modalità", value="splatoon3"),
            app_commands.Choice(name="World of Warcraft: reset settimanale", value="wow"),
        ]
    )
    async def turni(self, interaction: discord.Interaction, gioco: app_commands.Choice[str]) -> None:
        lingua = await lingua_interazione(interaction)
        await interaction.response.defer(ephemeral=True)
        if gioco.value == "wow":
            await interaction.followup.send(embed=embed_wow(datetime.now(timezone.utc), lingua), ephemeral=True)
            return
        dati = await tl.splatoon3(cache_esterna_repo, int(time.time()))
        if dati is None:
            await interaction.followup.send(t("turni_non_risponde", lingua), ephemeral=True)
            return
        await interaction.followup.send(embed=embed_splatoon(dati, lingua), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TurniGiochiCog(bot))
