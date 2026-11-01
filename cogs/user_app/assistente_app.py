"""
cogs/user_app/assistente_app.py
===============================
iYokai App: `/trova` cerca tra i comandi e i menu dell'app (senza AI) e `/assistente` è l'assistente personale con
l'AI, che conosce l'elenco delle funzioni dell'app. Con l'AI ferma o spenta dalla persona risponde `/trova`.
Il testo della domanda passa dallo snodo come testo di utente e non si salva (D19). Si carica solo sul client dell'app.
Funzioni coperte: SPEC §25.85, §25.86 (AI-R-092, AI-R-093)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.ai_servizio import AINonDisponibile, RichiestaAI, servizio_ai
from core.ai_testi_logic import riconosci_lingua
from core.command_search_logic import raccogli_comandi
from core.user_app_assistente_logic import ISTRUZIONI, elenco_per_ai, trova
from core.user_app_bot import e_istanza_app

logger = logging.getLogger("iyokai.user_app_assistente")

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)
NESSUNA_MENZIONE = discord.AllowedMentions.none()
VUOTO = "Non ho trovato nulla con queste parole: prova con altre, per esempio «nota», «promemoria» o «traduci»."


class AssistenteAppCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _comandi_e_menu(self) -> tuple[list, list[str]]:
        comandi = raccogli_comandi(self.bot.tree.get_commands(type=discord.AppCommandType.chat_input))
        menu = [m.name for m in self.bot.tree.get_commands(type=discord.AppCommandType.message)]
        return comandi, menu

    async def _ids(self) -> dict[str, int]:
        try:
            return {c.name: c.id for c in await self.bot.tree.fetch_commands()}
        except discord.HTTPException:
            return {}

    @app_commands.command(name="trova", description="Cerca una funzione di iYokai App: comandi e menu sul messaggio.")
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(cosa="Cosa vuoi fare, con parole tue")
    async def trova_funzione(self, interaction: discord.Interaction, cosa: app_commands.Range[str, 2, 100]) -> None:
        await interaction.response.defer(ephemeral=True)
        comandi, menu = self._comandi_e_menu()
        testo = trova(cosa, comandi, menu, await self._ids())
        await interaction.followup.send(testo or VUOTO, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @app_commands.command(name="assistente", description="Il tuo assistente personale: chiedi come fare una cosa.")
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(domanda="La tua domanda")
    async def assistente(self, interaction: discord.Interaction, domanda: app_commands.Range[str, 2, 500]) -> None:
        await interaction.response.defer(ephemeral=True)
        comandi, menu = self._comandi_e_menu()
        try:
            risposta = await servizio_ai().richiedi(RichiestaAI(
                user_id=interaction.user.id, funzione="app_assistente", tipo="chat", testo=domanda, guild_id=None,
                istruzioni=ISTRUZIONI + "\n\nFunzioni dell'app:\n" + elenco_per_ai(comandi, menu), messaggi_utenti=True,
                lingua=riconosci_lingua(domanda), riusa=False, conversazione=("app", interaction.user.id),
            ))
            testo = risposta.testo
        except AINonDisponibile as exc:
            testo = (trova(domanda, comandi, menu, await self._ids()) or VUOTO) + f"\n\n{exc.testo}"
        except Exception:  # noqa: BLE001 - database o fornitori in errore: si risponde senza AI
            logger.warning("Assistente dell'app non riuscito.", exc_info=True)
            testo = trova(domanda, comandi, menu, await self._ids()) or VUOTO
        await interaction.followup.send(testo[:2000], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app."""
    if e_istanza_app(bot):
        await bot.add_cog(AssistenteAppCog(bot))
