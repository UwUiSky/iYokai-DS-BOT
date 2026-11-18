"""
cogs/utility/schede.py
======================
`/utility scheda`: schede di un utente, del server, di un canale e di un
ruolo; elenco dei ruoli; membri con un ruolo; classifiche di anzianità;
permessi di un membro o del bot in un canale. I testi sono in
core/schede_logic.py; gli elenchi lunghi vanno a pagine.
Funzioni coperte: SPEC §14 (catalogo #128: UTL-195, 197-200, 202; #123: RUO-110-112); STA-058, 059, 060
"""

from __future__ import annotations

import asyncio
import re

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility._owner_pagine import invia_a_pagine
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per
from core.invio_file import invia_file
from core.server_stats_logic import tabella_in_csv
from core.schede_logic import (
    ANZIANITA,
    campi_canale,
    campi_emoji,
    campi_invito,
    leggi_emoji,
    righe_membri_csv,
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

    @comando_di_gruppo("utility", nome="membri", descrizione="I membri che hanno un ruolo, o tutti in un file.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(ruolo="Quale ruolo (vuoto: tutti, solo con il file)", file="Mandalo come file CSV (serve «Gestisci server»)")
    async def membri(self, interaction: discord.Interaction, ruolo: discord.Role | None = None, file: bool = False) -> None:
        # STA-058: l'elenco in un file, solo per chi gestisce il server (ci sono ID e date di ingresso di tutti)
        if file and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(await testo_per(interaction, "schede_file_serve_gestire_server"), ephemeral=True)
            return
        if ruolo is None and not file:
            await interaction.response.send_message(await testo_per(interaction, "schede_scegli_ruolo_o_file"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self._membri_pronti(interaction.guild)
        elenco = ruolo.members if ruolo is not None else interaction.guild.members
        if file:
            ordinati = sorted(elenco, key=lambda m: m.id)
            dati = await asyncio.to_thread(
                lambda: tabella_in_csv(["id", "nome", "bot", "entrato_il", "account_creato_il"], righe_membri_csv(ordinati), massimo=100_000)
            )
            await invia_file(interaction.followup.send, dati, "membri.csv", ephemeral=True, dividi=True)
            return
        righe = [f"{m.mention} — `{m.id}`" for m in sorted(elenco, key=lambda m: m.display_name.lower())]
        await invia_a_pagine(interaction, f"@{ruolo.name}: {len(righe)} membri", righe or ["Nessuno."], dopo_defer=True)

    @comando_di_gruppo("utility", nome="invito", descrizione="Scheda di un invito: server, canale, membri, scadenza.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(codice="Il codice o il link dell'invito")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def invito(self, interaction: discord.Interaction, codice: app_commands.Range[str, 2, 100]) -> None:
        # STA-059: solo ciò che Discord dà a chiunque abbia il codice; il codice si ripulisce prima di chiederlo
        try:
            pulito = discord.utils.resolve_invite(codice.strip()).code
        except ValueError:
            pulito = ""
        if not re.fullmatch(r"[A-Za-z0-9-]{2,32}", pulito):
            await interaction.response.send_message(await testo_per(interaction, "schede_invito_non_valido"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            invito = await self.bot.fetch_invite(pulito, with_counts=True, with_expiration=True)
        except discord.NotFound:
            await interaction.followup.send(await testo_per(interaction, "schede_invito_non_trovato"), ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "schede_invito_errore"), ephemeral=True)
            return
        await interaction.followup.send(
            embed=embed_da_campi(await testo_per(interaction, "schede_titolo_invito"), campi_invito(invito)),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo("utility", nome="emoji", descrizione="Scheda di un'emoji: ID, data, animata, immagine.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(emoji="L'emoji (anche personalizzata) o il suo ID")
    async def emoji(self, interaction: discord.Interaction, emoji: app_commands.Range[str, 1, 100]) -> None:
        # STA-059
        tipo, _nome, emoji_id, _animata = leggi_emoji(emoji)
        if tipo == "niente":
            await interaction.response.send_message(await testo_per(interaction, "schede_emoji_non_valida"), ephemeral=True)
            return
        trovata = self.bot.get_emoji(emoji_id) if emoji_id else None
        await interaction.response.send_message(
            embed=embed_da_campi(await testo_per(interaction, "schede_titolo_emoji"), campi_emoji(emoji, trovata, interaction.guild.id if interaction.guild else None)),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

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
