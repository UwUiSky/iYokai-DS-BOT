"""
cogs/fun/entertainment.py
============================
Mini-giochi (SPEC.md §16.1) e altri comandi di intrattenimento
classici (§16.8): testa/croce, dado, carta/forbici/sasso, palla
magica 8, barzelletta, citazione, curiosità.

Decisione tecnica IMPORTANTE, presa scrivendo questo file: il bot è
già a 96 comandi slash TOP-LEVEL su un limite GLOBALE di Discord di
100 (verificato con una prova reale — caricare tutti i cog insieme e
contare `bot.tree.get_commands()` — non solo letto sulla
documentazione). 7 nuovi comandi separati (coinflip/dice/rps/8ball/
joke/quote/fact) avrebbero sfondato il limite e fatto fallire in
silenzio la registrazione di un cog successivo in ordine di
caricamento (esattamente il bug già documentato in
tests/test_cog_manager_load_all.py per un nome duplicato — qui la
causa sarebbe stata il limite, non un doppione, ma l'effetto
identico: un cog che smette di funzionare senza errore visibile).
Per questo tutti i comandi di questo file vivono sotto UN SOLO
gruppo (`/fun ...`), che consuma un solo slot top-level indipendente
da quanti sotto-comandi contiene — lo stesso principio già seguito
altrove nel progetto per raggruppare comandi correlati (`/config`,
`/ticket-category`, ecc.), qui applicato per la prima volta come
misura di risparmio slot deliberata. Ship e Rate (§16.5/§16.7,
cogs/fun/ship_rate.py) restano comandi top-level a sé: sono già in
produzione, cambiarli in sotto-comandi ora sarebbe una rottura per
chi li usa già senza un guadagno di slot che serva adesso (restano
solo 2 di headroom). Qualunque comando FUTURO di §16 (image
manipulation, meme, animal, ricerca immagini) andrà sotto questo
stesso gruppo o un gruppo analogo, non come nuovo comando top-level.
"""

from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from core.classic_entertainment_logic import random_fact, random_joke, random_quote
from core.database import db
from core.minigames_logic import answer_8ball, flip_coin, play_rps, roll_dice
from core.premium import PremiumModule, registry

MODULE_FUN = "fun"

_RPS_CHOICE_DISPLAY = {"sasso": "🪨 Sasso", "carta": "📄 Carta", "forbici": "✂️ Forbici"}


class EntertainmentCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()

    fun_group = app_commands.Group(
        name="fun", description="Mini-giochi e intrattenimento (SPEC.md §16.1/§16.8)."
    )

    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False

        if not await db.is_module_active_for_guild(guild.id, MODULE_FUN):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return False
        return True

    @fun_group.command(name="coinflip", description="Lancia una moneta: testa o croce.")
    async def coinflip(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return

        risultato = flip_coin(self._rng)
        await interaction.response.send_message(f"🪙 **{risultato.upper()}**!")

    @fun_group.command(name="dice", description="Tira un dado.")
    @app_commands.describe(sides="Numero di facce del dado (default 6, minimo 2, massimo 1000)")
    async def dice(self, interaction: discord.Interaction, sides: int = 6) -> None:
        if not await self._modulo_attivo(interaction):
            return

        if sides < 2 or sides > 1000:
            await interaction.response.send_message(
                "Il dado deve avere tra 2 e 1000 facce.", ephemeral=True
            )
            return

        risultato = roll_dice(self._rng, sides=sides)
        await interaction.response.send_message(f"🎲 Hai tirato un **{risultato}** (d{sides}).")

    @fun_group.command(name="rps", description="Carta, forbici, sasso contro il bot.")
    @app_commands.describe(scelta="Sasso, carta o forbici")
    @app_commands.choices(
        scelta=[
            app_commands.Choice(name="Sasso", value="sasso"),
            app_commands.Choice(name="Carta", value="carta"),
            app_commands.Choice(name="Forbici", value="forbici"),
        ]
    )
    async def rps(self, interaction: discord.Interaction, scelta: app_commands.Choice[str]) -> None:
        if not await self._modulo_attivo(interaction):
            return

        scelta_bot, esito = play_rps(scelta.value, self._rng)

        if esito == "vittoria":
            titolo = "🎉 Hai vinto!"
        elif esito == "sconfitta":
            titolo = "😔 Hai perso."
        else:
            titolo = "🤝 Pareggio!"

        await interaction.response.send_message(
            f"{titolo}\nTu: {_RPS_CHOICE_DISPLAY[scelta.value]} — "
            f"Bot: {_RPS_CHOICE_DISPLAY[scelta_bot]}"
        )

    @fun_group.command(name="8ball", description="Fai una domanda alla palla magica 8.")
    @app_commands.describe(domanda="La tua domanda")
    async def eight_ball(self, interaction: discord.Interaction, domanda: str) -> None:
        if not await self._modulo_attivo(interaction):
            return

        risposta = answer_8ball(self._rng)
        embed = discord.Embed(
            title="🎱 Palla magica 8",
            description=f"**Domanda:** {domanda}\n**Risposta:** {risposta}",
            color=discord.Color.dark_purple(),
        )
        await interaction.response.send_message(embed=embed)

    @fun_group.command(name="joke", description="Racconta una barzelletta a caso.")
    async def joke(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.send_message(f"😄 {random_joke(self._rng)}")

    @fun_group.command(name="quote", description="Mostra una citazione a caso.")
    async def quote(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.send_message(f"💬 {random_quote(self._rng)}")

    @fun_group.command(name="fact", description="Mostra una curiosità a caso.")
    async def fact(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.send_message(f"🧠 {random_fact(self._rng)}")


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_FUN,
            display_name="Fun",
            description="Comandi di intrattenimento (Ship, Rate).",
            premium_capable=False,
        )
    )
    await bot.add_cog(EntertainmentCog(bot))
