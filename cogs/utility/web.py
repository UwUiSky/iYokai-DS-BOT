"""
cogs/utility/web.py
===================
Gruppo `/web`: Wikipedia, Wikizionario, numeri di emergenza (e, nei blocchi
seguenti, meteo, film, giochi, prezzi, accorciatore). Ogni richiesta esterna
passa da core/safe_http.py con defer() subito e cache.
Funzioni coperte: catalogo #128 UTL-215, 214, 220 (D69, B1)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import strumenti_rapidi_logic as logica
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_interazione, t


def embed_wiki(r: dict[str, str], fonte: str, colore: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=r["titolo"][:256], description=r["testo"][:4000], url=r["link"] or None, color=colore)
    if r.get("immagine"):
        embed.set_thumbnail(url=r["immagine"])
    embed.set_footer(text=fonte[:2048])
    return embed


async def _completa_paese(interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[str]]:
    paesi = logica.carica_emergenze()["paesi"]
    return [app_commands.Choice(name=p[:100], value=p[:60]) for p in logica.cerca_paesi(corrente, paesi)]


class WebCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("web", nome="wiki", descrizione="Il riassunto di una voce di Wikipedia.")
    @app_commands.describe(cerca="Che cosa cercare (massimo 100 caratteri)")
    async def wiki(self, interaction: discord.Interaction, cerca: app_commands.Range[str, 1, logica.MAX_RICERCA]) -> None:
        lingua = await lingua_interazione(interaction)
        await interaction.response.defer(ephemeral=True)
        r = await logica.cerca_wikipedia(logica.lingua_wiki(lingua), cerca)
        if r is None:
            await interaction.followup.send(t("wiki_non_trovata", lingua), ephemeral=True)
            return
        await interaction.followup.send(
            embed=embed_wiki(r, t("wiki_fonte", lingua), discord.Color.light_grey()), ephemeral=True
        )

    @comando_di_gruppo("web", nome="dizionario", descrizione="Il significato di una parola, da Wikizionario.")
    @app_commands.describe(parola="La parola (massimo 50 caratteri)")
    async def dizionario(
        self, interaction: discord.Interaction, parola: app_commands.Range[str, 1, logica.MAX_PAROLA]
    ) -> None:
        lingua = await lingua_interazione(interaction)
        await interaction.response.defer(ephemeral=True)
        r = await logica.cerca_parola(logica.lingua_wiki(lingua), parola)
        if r is None:
            await interaction.followup.send(t("dizionario_non_trovata", lingua), ephemeral=True)
            return
        await interaction.followup.send(
            embed=embed_wiki(r, t("dizionario_fonte", lingua), discord.Color.dark_grey()), ephemeral=True
        )

    @comando_di_gruppo("web", nome="emergenza", descrizione="I numeri di emergenza di un paese.")
    @app_commands.describe(paese="Il paese (scrivi per cercare)")
    @app_commands.autocomplete(paese=_completa_paese)
    async def emergenza(self, interaction: discord.Interaction, paese: app_commands.Range[str, 1, 60]) -> None:
        lingua = await lingua_interazione(interaction)
        dati = logica.carica_emergenze()
        nome = next(
            (p for p in dati["paesi"] if p.casefold() == paese.strip().casefold()), None
        ) or next(iter(logica.cerca_paesi(paese, dati["paesi"], 1)), None)
        if nome is None:
            await interaction.response.send_message(t("emergenza_non_trovato", lingua), ephemeral=True)
            return
        embed = discord.Embed(title=t("emergenza_titolo", lingua, paese=nome)[:256], color=discord.Color.red())
        for chiave, numero in dati["paesi"][nome].items():
            embed.add_field(name=t("emergenza_" + chiave, lingua)[:256], value=str(numero)[:1024])
        embed.set_footer(text=t("emergenza_fonte", lingua, data=dati.get("data", ""))[:2048])
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebCog(bot))
