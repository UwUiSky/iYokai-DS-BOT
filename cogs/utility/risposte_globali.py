"""
cogs/utility/risposte_globali.py
================================
Risposte automatiche valide in ogni server, gestite dall'owner del bot (massimo 20): `/owner system risposte-globali`.
Ogni server le può spegnere con `/admin-tag risposte globali`. Si innescano con la frase intera, senza badare alle maiuscole.
Funzioni coperte: catalogo #128 UTL-055 (D69, B18)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.autoresponder_logic import MAX_GLOBALI, jolly_validi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.i18n import testo_per
from core.repositories.autorisposte_globali_repo import autorisposte_globali_repo

_SCELTE = [app_commands.Choice(name=n, value=n) for n in ("aggiungi", "togli", "elenco")]


class RisposteGlobaliCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("owner", nome="risposte-globali", descrizione="Risposte automatiche comuni a tutti i server (massimo 20).",
                       sottogruppo=("system", "Sistema: codice, memoria, annunci e statistiche"))
    @app_commands.describe(azione="Cosa fare", innesco="La frase che fa scattare la risposta", risposta="Cosa risponde il bot",
                           numero="Il numero della risposta da togliere")
    @app_commands.choices(azione=_SCELTE)
    async def risposte_globali(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str], innesco: app_commands.Range[str, 1, 100] | None = None,
        risposta: app_commands.Range[str, 1, 1000] | None = None, numero: app_commands.Range[int, 1, 2_000_000_000] | None = None,
    ) -> None:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message("Comando riservato al proprietario del bot.", ephemeral=True)
            return
        if azione.value == "elenco":
            righe = [f"**{g.id}** · `{g.innesco[:60]}` → {g.risposta[:80]}" for g in await autorisposte_globali_repo.elenco()]
            await interaction.response.send_message(
                "\n".join(righe)[:1900] or await testo_per(interaction, "risposte_globali_nessuna"), ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())
            return
        if azione.value == "togli":
            fatta = numero is not None and await autorisposte_globali_repo.togli(numero)
            await interaction.response.send_message(
                await testo_per(interaction, "risposte_globali_tolta" if fatta else "risposte_globali_non_trovata"), ephemeral=True)
            return
        if innesco is None or risposta is None or not jolly_validi(innesco.strip()) or "*" in innesco:
            await interaction.response.send_message(await testo_per(interaction, "risposte_globali_servono"), ephemeral=True)
            return
        esito = await autorisposte_globali_repo.aggiungi(innesco.strip(), risposta.strip(), interaction.user.id)
        chiave = {"ok": "risposte_globali_aggiunta", "esiste": "risposte_globali_esiste", "pieno": "risposte_globali_piene"}[esito]
        await interaction.response.send_message(await testo_per(interaction, chiave, massimo=MAX_GLOBALI), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RisposteGlobaliCog(bot))
