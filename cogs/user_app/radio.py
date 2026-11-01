"""
cogs/user_app/radio.py
======================
Musica di iYokai App (SPEC B.8, C17, C18): le tue playlist (`/playlist …`) e `/radio ora`, che dice cosa suona
la radio iYokai e dà il link per cercare il testo. L'Activity «radio iYokai» sta nel pannello web
(core/web_panel_attivita.py). Si carica solo sul client dell'app (core/user_app_bot.py).
Funzioni coperte: SPEC B.8 (C17, C18; #107)
Dipende da: core/user_app_playlist.py, core/web_panel_attivita.py, core/repositories/user_app_repo.py
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.i18n import lingua_interazione, t, testo_per
from core.repositories.main_radio_repo import main_radio_repo
from core.repositories.user_app_repo import MAX_BRANI, MAX_PLAYLIST, user_app_repo
from core.ui_base import BaseView
from core.user_app_bot import e_istanza_app
from core.user_app_playlist import link_testo, nome_playlist, pulisci_brano, righe_playlist
from core.user_app_strumenti import ErroreStrumento
from core.web_panel_attivita import stato_radio

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)


async def _completa(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    righe = await user_app_repo.elenco_playlist(interaction.user.id)
    return [app_commands.Choice(name=r["nome"], value=r["nome"]) for r in righe if current.lower() in r["nome"]][:25]


async def _rispondi(interaction: discord.Interaction, chiave: str, **dati) -> None:
    await interaction.response.send_message(await testo_per(interaction, chiave, **dati), ephemeral=True)


class RadioCog(commands.Cog):
    playlist = app_commands.Group(
        name="playlist", description="Le tue playlist personali di brani.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )
    radio = app_commands.Group(
        name="radio", description="La radio iYokai: cosa suona adesso.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @playlist.command(name="crea", description="Crea una playlist vuota.")
    @app_commands.describe(nome="Il nome (lettere, numeri, - e _)")
    async def crea(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32]) -> None:
        try:
            nome = nome_playlist(nome)
        except ErroreStrumento as errore:
            await _rispondi(interaction, errore.chiave)
            return
        if await user_app_repo.crea_playlist(interaction.user.id, nome):
            await _rispondi(interaction, "app_playlist_creata", nome=nome)
        else:
            await _rispondi(interaction, "app_playlist_non_creata", massimo=MAX_PLAYLIST)

    @playlist.command(name="aggiungi", description="Aggiunge un brano a una tua playlist.")
    @app_commands.describe(nome="La playlist", brano="Titolo e artista del brano")
    @app_commands.autocomplete(nome=_completa)
    async def aggiungi(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32], brano: app_commands.Range[str, 1, 100]
    ) -> None:
        try:
            nome, brano = nome_playlist(nome), pulisci_brano(brano)
        except ErroreStrumento as errore:
            await _rispondi(interaction, errore.chiave)
            return
        esito = await user_app_repo.aggiungi_brano(interaction.user.id, nome, brano)
        chiave = {"ok": "app_playlist_aggiunto", "manca": "app_playlist_non_trovata", "piena": "app_playlist_piena"}[esito]
        await _rispondi(interaction, chiave, nome=nome, massimo=MAX_BRANI)

    @playlist.command(name="togli", description="Toglie un brano da una tua playlist.")
    @app_commands.describe(nome="La playlist", posizione="Il numero del brano (lo vedi con /playlist mostra)")
    @app_commands.autocomplete(nome=_completa)
    async def togli(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32], posizione: app_commands.Range[int, 1, 50]
    ) -> None:
        chiave = "app_playlist_tolto" if await user_app_repo.togli_brano(interaction.user.id, nome.strip().lower(), posizione) else "app_playlist_brano_assente"
        await _rispondi(interaction, chiave, nome=nome, posizione=posizione)

    @playlist.command(name="mostra", description="Mostra i brani di una tua playlist.")
    @app_commands.describe(nome="La playlist")
    @app_commands.autocomplete(nome=_completa)
    async def mostra(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32]) -> None:
        brani = await user_app_repo.playlist(interaction.user.id, nome.strip().lower())
        if brani is None:
            await _rispondi(interaction, "app_playlist_non_trovata", nome=nome)
            return
        lingua = await lingua_interazione(interaction)
        embed = discord.Embed(
            title=nome.strip().lower()[:256], description=righe_playlist(brani) or t("app_playlist_vuota", lingua),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{len(brani)}/{MAX_BRANI}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @playlist.command(name="elenco", description="Le tue playlist.")
    async def elenco(self, interaction: discord.Interaction) -> None:
        righe = await user_app_repo.elenco_playlist(interaction.user.id)
        lingua = await lingua_interazione(interaction)
        if not righe:
            await interaction.response.send_message(t("app_playlist_nessuna", lingua), ephemeral=True)
            return
        embed = discord.Embed(
            title=t("app_playlist_titolo", lingua), description="\n".join(f"`{r['nome']}` ({r['brani']})" for r in righe)[:4000],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{len(righe)}/{MAX_PLAYLIST}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @playlist.command(name="elimina", description="Elimina una tua playlist.")
    @app_commands.describe(nome="La playlist")
    @app_commands.autocomplete(nome=_completa)
    async def elimina(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32]) -> None:
        chiave = "app_playlist_eliminata" if await user_app_repo.rimuovi_playlist(interaction.user.id, nome.strip().lower()) else "app_playlist_non_trovata"
        await _rispondi(interaction, chiave, nome=nome)

    @radio.command(name="ora", description="Cosa suona adesso nella radio iYokai, con il link per cercare il testo.")
    async def ora(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        tracce = await main_radio_repo.list_tracks()
        stato = stato_radio(tracce, await main_radio_repo.get_state(), datetime.now(timezone.utc))
        lingua = await lingua_interazione(interaction)
        if not stato["attiva"]:
            await interaction.followup.send(t("app_radio_spenta", lingua), ephemeral=True)
            return
        embed = discord.Embed(
            title=stato["titolo"][:256], description=t("app_radio_ora", lingua, numero=stato["numero"], totale=stato["totale"]),
            color=discord.Color.blurple(),
        )
        vista = BaseView(timeout=None)
        vista.add_item(discord.ui.Button(label=t("app_radio_testo", lingua)[:80], url=link_testo(stato["titolo"])))
        await interaction.followup.send(embed=embed, view=vista, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app: il bot principale non riceve questi comandi."""
    if e_istanza_app(bot):
        await bot.add_cog(RadioCog(bot))
