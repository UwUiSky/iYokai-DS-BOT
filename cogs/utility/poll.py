"""
cogs/utility/poll.py
=======================
Poll (SPEC.md §14.15 — "usare il Poll nativo di Discord", come
indicato dallo schema stesso). Nessuna logica propria da estrarre:
voto, conteggio, chiusura automatica e visualizzazione dei risultati
sono TUTTI gestiti da Discord — questo cog è solo un'interfaccia
comando sopra discord.Poll, niente storage, niente stato nostro.
"""

from __future__ import annotations

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry

MODULE_POLL = "poll"

# Limiti dei sondaggi di Discord: 300 caratteri per la domanda, 55 per
# ogni risposta, 10 risposte. Dichiarati sulle opzioni del comando, è
# Discord stesso a rifiutare un testo troppo lungo con un suo messaggio.
TestoDomanda = app_commands.Range[str, 1, 300]
TestoRisposta = app_commands.Range[str, 1, 55]


class PollCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="poll", description="Crea un sondaggio (fino a 10 opzioni).")
    @app_commands.describe(
        question="La domanda del sondaggio (massimo 300 caratteri)",
        option1="Prima opzione (massimo 55 caratteri)",
        option2="Seconda opzione (massimo 55 caratteri)",
        option3="Terza opzione (facoltativa)",
        option4="Quarta opzione (facoltativa)",
        option5="Quinta opzione (facoltativa)",
        option6="Sesta opzione (facoltativa)",
        option7="Settima opzione (facoltativa)",
        option8="Ottava opzione (facoltativa)",
        option9="Nona opzione (facoltativa)",
        option10="Decima opzione (facoltativa)",
        duration_hours="Durata in ore (default 24, massimo 768 = 32 giorni)",
        multiple="Permetti di votare più di un'opzione",
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: TestoDomanda,
        option1: TestoRisposta,
        option2: TestoRisposta,
        option3: TestoRisposta | None = None,
        option4: TestoRisposta | None = None,
        option5: TestoRisposta | None = None,
        option6: TestoRisposta | None = None,
        option7: TestoRisposta | None = None,
        option8: TestoRisposta | None = None,
        option9: TestoRisposta | None = None,
        option10: TestoRisposta | None = None,
        duration_hours: app_commands.Range[int, 1, 768] = 24,
        multiple: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_POLL):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return

        opzioni = [
            o
            for o in (
                option1, option2, option3, option4, option5,
                option6, option7, option8, option9, option10,
            )
            if o is not None
        ]

        sondaggio = discord.Poll(
            question=question,
            duration=timedelta(hours=duration_hours),
            multiple=multiple,
        )
        for opzione in opzioni:
            sondaggio.add_answer(text=opzione)

        await interaction.response.send_message(poll=sondaggio)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_POLL,
            display_name="Poll",
            category="utility",
            description="Sondaggi tramite il sistema Poll nativo di Discord.",
            premium_capable=False,
        )
    )
    await bot.add_cog(PollCog(bot))
