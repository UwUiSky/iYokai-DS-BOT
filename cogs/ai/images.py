"""
cogs/ai/images.py
=================
Immagini: `/utility ai immagina` (generazione, con i bottoni Variazione e
Ingrandisci), `/utility ai ingrandisci` (ingrandisce e ripulisce un'immagine
caricata, sulla macchina del bot), `/utility ai pacchetto` (5 immagini in più
comprate con le monete del server). Quota settimanale per persona.
Funzioni coperte: SPEC §25.8, §25.60–§25.63 (AI-R-065..069; catalogo AI-005..008)

L'ingrandimento non usa un servizio AI: lo fa Pillow sul server del bot, così
funziona anche con l'AI ferma.
"""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import MODULO_AI, SOTTO_AI, chiedi, registra_modulo_ai, richiesta_da
from core.ai_immagini_logic import MAX_BYTES, ImmagineNonValida, ingrandisci
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.premium import requires_module
from core.repositories.ai_repo import ai_repo
from core.repositories.leveling_repo import leveling_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.ai_images")

IMMAGINI_PER_PACCHETTO = 5
_TIPI_IMMAGINE = ("image/png", "image/jpeg", "image/webp", "image/gif")


class _ImmagineView(BaseView):
    """Bottoni sotto l'immagine generata: solo chi l'ha chiesta li usa."""

    def __init__(self, autore_id: int, prompt: str, dati: bytes, variante: int = 1) -> None:
        super().__init__(timeout=600)
        self.autore_id = autore_id
        self.prompt = prompt
        self.dati = dati
        self.variante = variante

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message("Solo chi ha chiesto l'immagine usa questi bottoni.", ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    @discord.ui.button(label="Variazione", style=discord.ButtonStyle.primary)
    async def variazione(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        await genera(interaction, self.prompt, variante=self.variante + 1)

    @discord.ui.button(label="Ingrandisci", style=discord.ButtonStyle.secondary)
    async def ingrandisci(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(thinking=True)
        await _manda_ingrandita(interaction, self.dati)


async def _manda_ingrandita(interaction: discord.Interaction, dati: bytes) -> None:
    try:
        grande, estensione = ingrandisci(dati)
    except ImmagineNonValida as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return
    await interaction.followup.send(file=discord.File(io.BytesIO(grande), filename=f"ingrandita.{estensione}"))


async def genera(interaction: discord.Interaction, prompt: str, variante: int = 1) -> None:
    """Genera e manda l'immagine (la risposta deve essere già differita)."""
    testo = prompt if variante == 1 else f"{prompt} (variante {variante}, composizione diversa)"
    risposta, locale = await chiedi(richiesta_da(interaction, "immagina", "immagine", testo, riusa=False))
    if risposta is None or not risposta.immagine:
        await interaction.followup.send(locale or "Il servizio non ha restituito un'immagine.", ephemeral=True)
        return
    embed = discord.Embed(description=prompt[:300], color=discord.Color.blurple())
    embed.set_image(url="attachment://immagine.png")
    embed.set_footer(text="Immagine generata dall'AI")
    await interaction.followup.send(
        embed=embed, file=discord.File(io.BytesIO(risposta.immagine), filename="immagine.png"),
        view=_ImmagineView(interaction.user.id, prompt, risposta.immagine, variante),
    )


class AiImmaginiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("utility", nome="immagina", descrizione="Genera un'immagine da una descrizione.", sottogruppo=SOTTO_AI)
    @app_commands.describe(descrizione="Cosa disegnare")
    @requires_module(MODULO_AI)
    async def immagina(self, interaction: discord.Interaction, descrizione: app_commands.Range[str, 3, 500]) -> None:
        await interaction.response.defer(thinking=True)
        await genera(interaction, descrizione)

    @comando_di_gruppo("utility", nome="ingrandisci", descrizione="Ingrandisce e ripulisce un'immagine che carichi.", sottogruppo=SOTTO_AI)
    @app_commands.describe(immagine="PNG, JPEG, WEBP o GIF (fino a 10 MiB)")
    async def ingrandisci(self, interaction: discord.Interaction, immagine: discord.Attachment) -> None:
        if (immagine.content_type or "").split(";")[0] not in _TIPI_IMMAGINE or immagine.size > MAX_BYTES:
            await interaction.response.send_message("Serve un'immagine PNG, JPEG, WEBP o GIF fino a 10 MiB.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            dati = await immagine.read()
        except discord.HTTPException:
            await interaction.followup.send("Non riesco a scaricare l'immagine.", ephemeral=True)
            return
        await _manda_ingrandita(interaction, dati)

    @comando_di_gruppo("utility", nome="pacchetto", descrizione="Compra 5 immagini AI in più con le monete del server.", sottogruppo=SOTTO_AI)
    @requires_module(MODULO_AI)
    async def pacchetto(self, interaction: discord.Interaction) -> None:
        cfg = await ai_repo.get_config(interaction.guild_id)
        prezzo = cfg.prezzo_pacchetto_immagini
        if prezzo <= 0:
            await interaction.response.send_message("In questo server i pacchetti di immagini non sono in vendita.", ephemeral=True)
            return
        if not await leveling_repo.spend_coins(interaction.guild_id, interaction.user.id, prezzo):
            await interaction.response.send_message(f"Servono {prezzo} monete.", ephemeral=True)
            return
        totale = await ai_repo.crediti_aggiungi(interaction.guild_id, interaction.user.id, IMMAGINI_PER_PACCHETTO)
        await interaction.response.send_message(
            f"Fatto: {IMMAGINI_PER_PACCHETTO} immagini in più per {prezzo} monete. Ne hai {totale} da usare "
            "quando finisce la quota della settimana.", ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiImmaginiCog(bot))
