"""
cogs/ai/segnalazioni.py
=======================
Etichetta (categoria e urgenza) sulle segnalazioni degli utenti. La chiama `/utility report`; lo staff può
cambiare la categoria con il menu sotto il messaggio. L'AI propone, non punisce.
Funzioni coperte: SPEC §25.38 (AI-R-040)
"""

from __future__ import annotations

import discord
from discord.ext import commands

from cogs.ai._comune import chiedi, registra_modulo_ai
from core import segnalazioni_logic as logica
from core.ai_servizio import RichiestaAI
from core.command_access import Livello, puo_usare
from core.ui_base import BaseView

CAMPO = "Etichetta"
ID_MENU = "airep:cat"


async def etichetta_segnalazione(guild_id: int, user_id: int, motivo: str, scelta: str | None = None) -> logica.Etichetta:
    """Se la persona ha scelto la categoria l'AI non serve; altrimenti l'AI propone, e senza AI valgono le parole."""
    proposta = None
    if scelta not in logica.CATEGORIE:
        risposta, _ = await chiedi(RichiestaAI(
            user_id=user_id, funzione="segnalazione_etichetta", tipo="giudizio", guild_id=guild_id, fascia="bassa",
            testo=f"Segnalazione: «{motivo}»", istruzioni=logica.ISTRUZIONI, messaggi_utenti=True, riusa=False,
            max_token=60, conta_utente=False,
        ))
        proposta = logica.leggi_etichetta(risposta.testo) if risposta else None
    return logica.etichetta_finale(scelta, proposta, motivo)


class _Categoria(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            custom_id=ID_MENU, placeholder="Cambia categoria (staff)",
            options=[discord.SelectOption(label=c.capitalize(), value=c) for c in logica.CATEGORIE],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await puo_usare(interaction, Livello.MOD):
            await interaction.response.send_message("Lo può cambiare solo lo staff.", ephemeral=True)
            return
        embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else None
        if embed is None:
            await interaction.response.send_message("Messaggio non valido.", ephemeral=True)
            return
        scelta = self.values[0]
        for i, campo in enumerate(embed.fields):
            if campo.name == CAMPO:
                urgenza = campo.value.split("urgenza ")[-1].split(" ")[0] if "urgenza " in campo.value else "bassa"
                embed.set_field_at(i, name=CAMPO, value=f"{scelta} · urgenza {urgenza} (cambiata dallo staff)", inline=False)
                break
        await interaction.response.edit_message(embed=embed)


class EtichettaView(BaseView):
    """Menu persistente sotto la segnalazione (id fisso): lo staff cambia la categoria."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(_Categoria())


class AiSegnalazioniCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(EtichettaView())


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiSegnalazioniCog(bot))
