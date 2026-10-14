"""
cogs/ai/lore.py
===============
Lore e personaggi: `/utility ai lore` (scheda su un nome o un luogo, scritta
secondo la lore del server e salvata per riusarla), `/utility ai crea-personaggio`
(biografia, tratti, gusti, fatti), `/utility ai personaggio` (chatta con un
personaggio installato dall'admin, con la memoria corta).
Funzioni coperte: SPEC §25.48, §25.57, §25.58, §25.89 (AI-R-053, AI-R-062, AI-R-063, AI-R-096; catalogo AI-014, AI-015)

Senza AI: la scheda di lore mostra il testo della lore del server; il personaggio
risponde con la sua biografia.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import (
    MODULO_AI, NESSUNA_MENZIONE, SOTTO_AI, chiedi, embed_risposta, registra_modulo_ai, richiesta_da, taglia,
)
from core.ai_testi_logic import ISTRUZIONI, riconosci_lingua, testo_lore
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.premium import requires_module
from core.repositories.ai_repo import Personaggio, ai_repo
from core.ui_base import BaseModal

MAX_PERSONAGGI = 25


def scheda_personaggio(p: Personaggio) -> str:
    parti = [f"Nome: {p.nome}", f"Biografia: {p.biografia}", f"Tratti: {p.tratti}", f"Gusti: {p.gusti}", f"Fatti: {p.fatti}"]
    return "\n".join(x for x in parti if not x.endswith(": "))


class _PersonaggioModal(BaseModal, title="Nuovo personaggio AI"):
    nome = discord.ui.TextInput(label="Nome", max_length=40)
    biografia = discord.ui.TextInput(label="Biografia", style=discord.TextStyle.paragraph, max_length=800)
    tratti = discord.ui.TextInput(label="Carattere", required=False, max_length=300)
    gusti = discord.ui.TextInput(label="Cosa ama e cosa odia", required=False, max_length=300)
    fatti = discord.ui.TextInput(label="Fatti da ricordare", style=discord.TextStyle.paragraph, required=False, max_length=600)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if len(await ai_repo.personaggi(interaction.guild_id)) >= MAX_PERSONAGGI:
            await interaction.response.send_message(f"Il server ha già {MAX_PERSONAGGI} personaggi.", ephemeral=True)
            return
        creato = await ai_repo.personaggio_crea(
            interaction.guild_id, interaction.user.id, self.nome.value.strip(),
            biografia=self.biografia.value.strip(), tratti=self.tratti.value.strip(),
            gusti=self.gusti.value.strip(), fatti=self.fatti.value.strip(),
        )
        if creato is None:
            await interaction.response.send_message("Esiste già un personaggio con questo nome.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Personaggio «{creato.nome}» creato. Un amministratore lo rende disponibile con `/ai personaggio`.",
            ephemeral=True, allowed_mentions=NESSUNA_MENZIONE,
        )


class AiLoreCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _installati(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        elenco = await ai_repo.personaggi(interaction.guild_id, solo_installati=True)
        return [app_commands.Choice(name=p.nome, value=p.nome) for p in elenco if current.lower() in p.nome.lower()][:25]

    @comando_di_gruppo("utility", nome="lore", descrizione="Scheda di lore su un nome, un luogo o uno yokai.", sottogruppo=SOTTO_AI)
    @app_commands.describe(argomento="Di cosa vuoi la scheda")
    @requires_module(MODULO_AI)
    async def lore(self, interaction: discord.Interaction, argomento: app_commands.Range[str, 2, 100]) -> None:
        await interaction.response.defer(ephemeral=True)
        risposta, locale = await chiedi(richiesta_da(
            interaction, "lore", "testo", argomento,
            istruzioni="Scrivi una breve scheda di lore (max 120 parole) sull'argomento, coerente con l'ambientazione.",
            lingua=riconosci_lingua(argomento),
        ))
        if risposta is None:
            cfg = await ai_repo.get_config(interaction.guild_id)
            lore = testo_lore(cfg.lore_tema, cfg.lore_testo)
            await interaction.followup.send(f"{locale}\n\n{taglia(lore, 1500)}" if lore else locale, ephemeral=True)
            return
        await interaction.followup.send(embed=embed_risposta(argomento, risposta.testo, da_cache=risposta.da_cache), ephemeral=True)

    @comando_di_gruppo("utility", nome="crea-personaggio", descrizione="Crea un personaggio AI con cui chattare.", sottogruppo=SOTTO_AI)
    @requires_module(MODULO_AI)
    async def crea_personaggio(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_PersonaggioModal())

    @comando_di_gruppo("utility", nome="personaggio", descrizione="Parla con un personaggio AI del server.", sottogruppo=SOTTO_AI)
    @app_commands.describe(nome="Il personaggio", messaggio="Cosa gli dici")
    @app_commands.autocomplete(nome=_installati)
    @requires_module(MODULO_AI)
    async def personaggio(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 40], messaggio: app_commands.Range[str, 1, 1000]
    ) -> None:
        p = await ai_repo.personaggio(interaction.guild_id, nome)
        if p is None or not p.installato:
            await interaction.response.send_message("Personaggio non disponibile in questo server.", ephemeral=True)
            return
        await interaction.response.defer()
        risposta, locale = await chiedi(richiesta_da(
            interaction, "personaggio", "chat", messaggio,
            istruzioni=f"{ISTRUZIONI['personaggio']}\n{scheda_personaggio(p)}", lingua=riconosci_lingua(messaggio),
            conversazione=(interaction.guild_id, interaction.channel_id, interaction.user.id, p.id),
        ))
        testo = risposta.testo if risposta else f"*{taglia(p.biografia, 500)}*\n-# {locale}"
        await interaction.followup.send(
            taglia(f"**{p.nome}:** {testo}", 2000), allowed_mentions=NESSUNA_MENZIONE
        )


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiLoreCog(bot))
