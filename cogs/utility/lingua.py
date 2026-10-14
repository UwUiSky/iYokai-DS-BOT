"""
cogs/utility/lingua.py
======================
`/utility lingua`: ogni utente sceglie la sua lingua (italiano o inglese) per le risposte
che vede solo lui. Quelle pubbliche seguono la lingua del server (`/admin lingua set`).
Funzioni coperte: SPEC §21 (NF-06, #77). Dati: tabella `user_language` (0130, registro dei dati).
Nessun controllo di modulo: è una preferenza personale, non una funzione del server.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import imposta_lingua_utente, lingua_server, lingua_utente, t


class LinguaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "utility",
        nome="lingua",
        descrizione="Mostra o cambia la tua lingua personale (italiano o inglese).",
    )
    @app_commands.describe(lingua="Lingua per le risposte che vedi solo tu; vuoto = mostra quella attuale")
    @app_commands.choices(
        lingua=[
            app_commands.Choice(name="Italiano", value="it"),
            app_commands.Choice(name="English", value="en"),
            app_commands.Choice(name="Lingua del server / Server language", value="server"),
        ]
    )
    async def lingua(
        self, interaction: discord.Interaction, lingua: app_commands.Choice[str] | None = None
    ) -> None:
        server = await lingua_server(interaction.guild.id if interaction.guild else None)
        if lingua is None:
            mia = await lingua_utente(interaction.user.id)
            testo = (
                t("lingua_utente_attuale", mia, lingua=mia, server=server)
                if mia
                else t("lingua_utente_nessuna", server, server=server)
            )
        else:
            salvata = await imposta_lingua_utente(interaction.user.id, lingua.value)
            testo = (
                t("lingua_utente_impostata", salvata, lingua=salvata)
                if salvata
                else t("lingua_utente_azzerata", server)
            )
        await interaction.response.send_message(testo, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LinguaCog(bot))
