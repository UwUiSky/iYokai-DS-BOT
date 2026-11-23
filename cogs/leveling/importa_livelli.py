"""
cogs/leveling/importa_livelli.py
================================
/admin-livelli importa: carica gli XP da un file JSON o CSV che l'admin ha esportato da un altro bot (mai da API di
altri bot). Ogni campo si controlla prima di scrivere; l'import non toglie mai XP e si può ripetere. Funzione a
livello di abbonamento scelto dall'owner (D57, D71: di base premium).
Funzioni coperte: LIV-072
Dipende da: core/livelli_import_logic.py, core/repositories/livelli_import_repo.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.azzeramenti import _avvia_sincronia
from cogs.leveling.leveling import _comando_rifiutato
from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.livelli_import_logic import MAX_BYTE_FILE, MAX_RIGHE, ImportNonValido, leggi_file
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.livelli_import_repo import livelli_import_repo

logger = logging.getLogger("iyokai.livelli_import")


class ImportaLivelliCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    @comando_di_gruppo("admin-livelli", nome="importa", descrizione="Carica gli XP da un file JSON o CSV esportato da un altro bot.", sottogruppo=SOTTOGRUPPI["admin-livelli azzera"])
    @app_commands.describe(file=f"File .json o .csv con id e xp di ogni persona (al massimo {MAX_RIGHE} righe, {MAX_BYTE_FILE // 1024 // 1024} MB)")
    async def importa(self, interaction: discord.Interaction, file: discord.Attachment) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not interaction.permissions.manage_guild:
            await interaction.response.send_message(await testo_per(interaction, "liv_import_permesso"), ephemeral=True)
            return
        if file.size > MAX_BYTE_FILE:
            await interaction.response.send_message(await testo_per(interaction, "liv_import_errore", errore="File troppo grande."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            righe = leggi_file(await file.read(), file.filename)
        except ImportNonValido as errore:
            await interaction.followup.send(await testo_per(interaction, "liv_import_errore", errore=str(errore)[:500]), ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "liv_import_errore", errore="File non scaricabile."), ephemeral=True)
            return
        i = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni
        cambiate, uguali = await livelli_import_repo.importa(interaction.guild.id, righe, tetto_livello=i.max_level, formula=i.formula)
        logger.info("Import dei livelli: server %s, staff %s, %s righe, %s cambiate.", interaction.guild.id, interaction.user.id, len(righe), cambiate)
        _avvia_sincronia(self.bot, interaction.guild, [r.user_id for r in righe][:5000])
        await interaction.followup.send(await testo_per(interaction, "liv_import_ok", cambiate=cambiate, uguali=uguali), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImportaLivelliCog(bot))
