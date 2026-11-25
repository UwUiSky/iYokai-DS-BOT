"""
cogs/music/paese.py
===================
Paese globale delle ricerche musicali (MUS-015, D111): `/owner-radio paese`. Di base nessun limite (brani ascoltabili
in tutto il mondo); i server possono scegliere il loro con `/admin-musica impostazioni paese:`.
Funzioni coperte: SPEC §9 (catalogo MUS-015)
Dipende da: core/music_paese_logic.py, core/repositories/music_cartella_repo.py (impostazioni globali dell'owner)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.i18n import testo_per
from core.music_paese_logic import imposta_paese_globale, paese_globale, paese_valido
from core.repositories.music_cartella_repo import CHIAVE_PAESE, music_cartella_repo

logger = logging.getLogger("iyokai.music.paese")

RADIO = ("radio", "Radio 24/7 condivisa del bot")


async def carica_paese_globale() -> None:
    """Rimette in uso la scelta dell'owner (a ogni avvio)."""
    imposta_paese_globale(await music_cartella_repo.leggi_impostazione(CHIAVE_PAESE))


class MusicPaeseCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        try:
            await carica_paese_globale()
        except Exception:
            logger.exception("Lettura del paese globale delle ricerche non riuscita.")

    @comando_di_gruppo("owner-radio", nome="paese", descrizione="Paese delle ricerche musicali (di base nessuno).")
    @app_commands.describe(codice="2 lettere (es. IT); «-» toglie il limite")
    async def paese(self, interaction: discord.Interaction, codice: app_commands.Range[str, 1, 2] | None = None) -> None:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message(await testo_per(interaction, "owner_solo_proprietario"), ephemeral=True)
            return
        if codice is None:
            attuale = paese_globale()
            chiave = "music_paese_globale_stato" if attuale else "music_paese_globale_tolto"
            await interaction.response.send_message(await testo_per(interaction, chiave, paese=attuale or ""), ephemeral=True)
            return
        if codice.strip() == "-":
            await music_cartella_repo.scrivi_impostazione(CHIAVE_PAESE, None, interaction.user.id)
            imposta_paese_globale(None)
            await interaction.response.send_message(await testo_per(interaction, "music_paese_globale_tolto"), ephemeral=True)
            return
        pulito = paese_valido(codice)
        if pulito is None:
            await interaction.response.send_message(await testo_per(interaction, "music_paese_non_valido"), ephemeral=True)
            return
        await music_cartella_repo.scrivi_impostazione(CHIAVE_PAESE, pulito, interaction.user.id)
        imposta_paese_globale(pulito)
        await interaction.response.send_message(
            await testo_per(interaction, "music_paese_globale_impostato", paese=pulito), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicPaeseCog(bot))
