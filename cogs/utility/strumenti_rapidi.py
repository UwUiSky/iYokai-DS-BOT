"""
cogs/utility/strumenti_rapidi.py
================================
`/utility caratteri`, `/utility cronometro` (bottoni Giro e Ferma, nessun dato salvato:
l'inizio sta nel custom_id) e `/utility novita` (file data/novita/<lingua>.json).
Funzioni coperte: catalogo #128 UTL-203, 212, 221 (D69, B1)
"""

from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from core import strumenti_rapidi_logic as logica
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_interazione, t
from core.ui_base import BaseView


class BottoneCronometro(
    discord.ui.DynamicItem[discord.ui.Button], template=r"crono:(?P<a>giro|ferma):(?P<i>[0-9]+)"
):
    def __init__(self, azione: str, inizio: int, lingua: str = "it") -> None:
        super().__init__(
            discord.ui.Button(
                label=t("crono_bottone_" + azione, lingua)[:80],
                style=discord.ButtonStyle.primary if azione == "giro" else discord.ButtonStyle.danger,
                custom_id=logica.id_cronometro(azione, inizio),
            )
        )
        self.azione = azione
        self.inizio = inizio

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["a"], int(match["i"]), await lingua_interazione(interaction))

    async def callback(self, interaction: discord.Interaction) -> None:
        contenuto = interaction.message.content if interaction.message else ""
        if self.azione == "ferma":
            await interaction.response.edit_message(content=logica.ferma_cronometro(contenuto, self.inizio), view=None)
            return
        nuovo, accettato = logica.aggiungi_giro(contenuto, self.inizio)
        if not accettato:
            await interaction.response.send_message(
                t("crono_giri_pieni", await lingua_interazione(interaction), massimo=logica.MAX_GIRI), ephemeral=True
            )
            return
        await interaction.response.edit_message(content=nuovo)


def vista_cronometro(inizio: int, lingua: str) -> discord.ui.View:
    # Le due voci sono DynamicItem: sopravvivono al riavvio perché si ricostruiscono dal custom_id.
    vista = BaseView(timeout=None)
    vista.add_item(BottoneCronometro("giro", inizio, lingua))
    vista.add_item(BottoneCronometro("ferma", inizio, lingua))
    return vista


class StrumentiRapidiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.add_dynamic_items(BottoneCronometro)

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(BottoneCronometro)
        await super().cog_unload()

    @comando_di_gruppo("utility", nome="caratteri", descrizione="Nome, codice e categoria Unicode dei caratteri di un testo.")
    @app_commands.describe(testo="Il testo da guardare (massimo 100 caratteri)")
    async def caratteri(
        self, interaction: discord.Interaction, testo: app_commands.Range[str, 1, logica.MAX_TESTO_CARATTERI]
    ) -> None:
        lingua = await lingua_interazione(interaction)
        righe, tagliati = logica.righe_caratteri(testo)
        if not righe:
            await interaction.response.send_message(t("caratteri_vuoto", lingua), ephemeral=True)
            return
        embed = discord.Embed(title=t("caratteri_titolo", lingua)[:256], color=discord.Color.blurple())
        for nome, valore in righe:
            embed.add_field(name=nome[:256], value=valore[:1024])
        if tagliati:
            embed.set_footer(text=t("caratteri_tagliati", lingua, n=tagliati)[:2048])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("utility", nome="cronometro", descrizione="Un cronometro con i bottoni Giro e Ferma.")
    async def cronometro(self, interaction: discord.Interaction) -> None:
        lingua = await lingua_interazione(interaction)
        inizio = int(time.time())
        await interaction.response.send_message(
            logica.corpo_cronometro(inizio, []),
            view=vista_cronometro(inizio, lingua),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo("utility", nome="novita", descrizione="Le ultime novità del bot.")
    @app_commands.describe(pagina="Quale pagina (10 voci per pagina)")
    async def novita(self, interaction: discord.Interaction, pagina: app_commands.Range[int, 1, 50] = 1) -> None:
        lingua = await lingua_interazione(interaction)
        voci, pagine = logica.pagina_novita(logica.carica_novita(lingua), pagina - 1)
        if not voci:
            await interaction.response.send_message(t("novita_vuote", lingua), ephemeral=True)
            return
        embed = discord.Embed(title=t("novita_titolo", lingua)[:256], color=discord.Color.blurple())
        for v in voci:
            embed.add_field(
                name=f"{v.get('data', '')} · {v['titolo']}"[:256], value=str(v.get("testo", "—"))[:1024], inline=False
            )
        embed.set_footer(text=t("novita_pagina", lingua, p=min(pagina, pagine), n=pagine)[:2048])
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StrumentiRapidiCog(bot))
