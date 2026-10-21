"""
cogs/utility/schede.py
======================
`/utility scheda`: schede di un utente, del server, di un canale e di un
ruolo; elenco dei ruoli; membri con un ruolo; classifiche di anzianità;
permessi di un membro o del bot in un canale. I testi sono in
core/schede_logic.py; gli elenchi lunghi vanno a pagine.
Funzioni coperte: SPEC §14 (catalogo #128: UTL-195, 197-200, 202; #123: RUO-110-112)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility._owner_pagine import invia_a_pagine
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.schede_logic import (
    ANZIANITA,
    campi_canale,
    campi_ruolo,
    campi_server,
    campi_utente,
    classifica_anzianita,
    righe_permessi,
    righe_ruoli,
)

SOTTOGRUPPO = ("scheda", "Schede di utenti, server, canali e ruoli")


def embed_da_campi(titolo: str, campi: list[tuple[str, str]], miniatura: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=titolo[:256], color=discord.Color.blurple())
    for nome, valore in campi[:25]:
        embed.add_field(name=nome[:256], value=(valore or "—")[:1024], inline=len(valore) < 40)
    if miniatura:
        embed.set_thumbnail(url=miniatura)
    return embed


class SchedeCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    async def _membri_pronti(guild: discord.Guild) -> None:
        """I membri del server in cache: per i server grandi Discord li manda a pezzi."""
        if not guild.chunked:
            await guild.chunk()

    @comando_di_gruppo("utility", nome="utente", descrizione="Scheda di un membro: ID, date e ruoli.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(membro="Di chi (vuoto = tu)")
    async def utente(self, interaction: discord.Interaction, membro: discord.Member | None = None) -> None:
        membro = membro or interaction.user
        embed = embed_da_campi(str(membro), campi_utente(membro), membro.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("utility", nome="server", descrizione="Scheda del server: proprietario, data, numeri, boost.", sottogruppo=SOTTOGRUPPO)
    async def server(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        icona = guild.icon.url if guild.icon else None
        await interaction.response.send_message(embed=embed_da_campi(guild.name, campi_server(guild), icona), ephemeral=True)

    @comando_di_gruppo("utility", nome="canale", descrizione="Scheda di un canale.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(canale="Quale canale (vuoto = questo)")
    async def canale(self, interaction: discord.Interaction, canale: discord.abc.GuildChannel | None = None) -> None:
        canale = canale or interaction.channel
        await interaction.response.send_message(embed=embed_da_campi(f"#{canale.name}", campi_canale(canale)), ephemeral=True)

    @comando_di_gruppo("utility", nome="ruolo", descrizione="Scheda di un ruolo: membri, colore, data, permessi.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(ruolo="Quale ruolo")
    async def ruolo(self, interaction: discord.Interaction, ruolo: discord.Role) -> None:
        await interaction.response.defer(ephemeral=True)
        await self._membri_pronti(interaction.guild)
        await interaction.followup.send(embed=embed_da_campi(f"@{ruolo.name}", campi_ruolo(ruolo)), ephemeral=True)

    @comando_di_gruppo("utility", nome="ruoli", descrizione="Tutti i ruoli con ID, membri e colore.", sottogruppo=SOTTOGRUPPO)
    async def ruoli(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self._membri_pronti(interaction.guild)
        righe = righe_ruoli(interaction.guild.roles) or ["Nessun ruolo."]
        await invia_a_pagine(interaction, f"Ruoli ({len(righe)})", righe, dopo_defer=True)

    @comando_di_gruppo("utility", nome="membri", descrizione="I membri che hanno un ruolo.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(ruolo="Quale ruolo")
    async def membri(self, interaction: discord.Interaction, ruolo: discord.Role) -> None:
        await interaction.response.defer(ephemeral=True)
        await self._membri_pronti(interaction.guild)
        righe = [f"{m.mention} — `{m.id}`" for m in sorted(ruolo.members, key=lambda m: m.display_name.lower())]
        await invia_a_pagine(interaction, f"@{ruolo.name}: {len(righe)} membri", righe or ["Nessuno."], dopo_defer=True)

    @comando_di_gruppo("utility", nome="anzianita", descrizione="Account più vecchi o nuovi, primi o ultimi entrati.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(tipo="Quale classifica")
    @app_commands.choices(tipo=[app_commands.Choice(name=v[0], value=k) for k, v in ANZIANITA.items()])
    async def anzianita(self, interaction: discord.Interaction, tipo: str) -> None:
        await interaction.response.defer(ephemeral=True)
        await self._membri_pronti(interaction.guild)
        righe = classifica_anzianita(interaction.guild.members, tipo) or ["Nessuno."]
        await invia_a_pagine(interaction, ANZIANITA[tipo][0], righe, dopo_defer=True)

    @comando_di_gruppo("utility", nome="permessi", descrizione="Permessi di un membro o del bot in un canale.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(membro="Di chi (vuoto = il bot)", canale="Dove (vuoto = questo canale)")
    async def permessi(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
        canale: discord.abc.GuildChannel | None = None,
    ) -> None:
        membro = membro or interaction.guild.me
        canale = canale or interaction.channel
        concessi, mancanti = righe_permessi(canale.permissions_for(membro))
        embed = embed_da_campi(
            f"Permessi di {membro.display_name} in #{canale.name}",
            [("Concessi", concessi), ("Mancanti", mancanti)],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SchedeCog(bot))
