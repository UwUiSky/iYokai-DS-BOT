"""
cogs/music/mondo.py
===================
Scoprire musica: `/music radio` cerca stazioni di tutto il mondo (MUS-010), `/music genere` apre il menu delle
playlist per genere scelte dall'owner (MUS-014).
Funzioni coperte: SPEC §9 (catalogo MUS-010, MUS-014)
Dipende da: cogs/music/player.py (MusicCog.accoda e controlli comuni), core/music_radio_mondo.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_interazione, t, testo_per
from core.music_generi_logic import raggruppa
from core.music_mondo_view import GenereView, RadioMondoView, intestazione_pagina
from core.music_radio_mondo import NOME_MAX, cerca_stazioni, nome_ricerca_valido
from core.music_sound_logic import PausaUtente
from core.repositories.music_generi_repo import music_generi_repo

logger = logging.getLogger("iyokai.music.mondo")

PAUSA_RICERCA = 3.0  # secondi tra due ricerche dello stesso utente


class MusicMondoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pausa_ricerche = PausaUtente(pausa=PAUSA_RICERCA)

    def _musica(self):
        return self.bot.get_cog("MusicCog")

    @comando_di_gruppo("music", nome="radio", descrizione="Cerca una radio da tutto il mondo e la mette in coda.")
    @app_commands.describe(nome="Parte del nome della stazione (2-60 caratteri)")
    async def radio(self, interaction: discord.Interaction, nome: app_commands.Range[str, 2, NOME_MAX]) -> None:
        musica = self._musica()
        if musica is None or not await musica.controlli_base(interaction):
            return
        pulito = nome_ricerca_valido(nome)
        if pulito is None:
            await interaction.response.send_message(await testo_per(interaction, "mondo_radio_nome_non_valido"), ephemeral=True)
            return
        resta = self.pausa_ricerche.resta(interaction.guild.id, interaction.user.id)
        if resta > 0:
            await interaction.response.send_message(
                await testo_per(interaction, "mondo_radio_riprova", secondi=int(resta) + 1), ephemeral=True
            )
            return
        self.pausa_ricerche.segna(interaction.guild.id, interaction.user.id)  # prima del primo await lento
        await interaction.response.defer(ephemeral=True)
        lingua = await lingua_interazione(interaction)
        dati = await cerca_stazioni(pulito, 0)
        if dati is None:
            await interaction.followup.send(t("mondo_radio_errore", lingua), ephemeral=True)
            return
        if not dati.stazioni:
            await interaction.followup.send(t("mondo_radio_nessuna", lingua, nome=pulito), ephemeral=True)
            return

        async def cerca(n: str, pagina: int):
            resto = self.pausa_ricerche.resta(interaction.guild.id, interaction.user.id)
            if resto > 0:  # niente raffica di pagine: la memoria risponde comunque alle pagine già viste
                return await cerca_stazioni(n, pagina, scarica=_solo_memoria)
            self.pausa_ricerche.segna(interaction.guild.id, interaction.user.id)
            return await cerca_stazioni(n, pagina)

        async def avvia(inter: discord.Interaction, stazione) -> None:
            if not await musica.controlli_base(inter):
                return
            await inter.response.defer(ephemeral=True)
            await musica.accoda(
                inter.guild, inter.user, stazione.url, inter.followup.send, interaction=inter,
            )

        vista = RadioMondoView(interaction.user.id, pulito, 0, dati, lingua, cerca, avvia)
        await interaction.followup.send(intestazione_pagina(pulito, 0, dati, lingua), view=vista, ephemeral=True)

    @comando_di_gruppo("music", nome="genere", descrizione="Scegli una playlist per genere dal menu.")
    async def genere(self, interaction: discord.Interaction) -> None:
        musica = self._musica()
        if musica is None or not await musica.controlli_base(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        lingua = await lingua_interazione(interaction)
        gruppi = raggruppa(await music_generi_repo.elenco())
        if not gruppi:
            await interaction.followup.send(t("mondo_genere_nessuno", lingua), ephemeral=True)
            return

        async def avvia(inter: discord.Interaction, voce) -> None:
            if not await musica.controlli_base(inter):
                return
            await inter.response.defer(ephemeral=True)
            await musica.accoda(inter.guild, inter.user, voce.link, inter.followup.send, interaction=inter)

        vista = GenereView(interaction.user.id, gruppi, lingua, avvia)
        await interaction.followup.send(vista.intestazione(), view=vista, ephemeral=True)


async def _solo_memoria(url: str, *, max_bytes: int):
    """Durante la pausa non si esce in rete: solo ciò che è già in memoria."""
    return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicMondoCog(bot))
