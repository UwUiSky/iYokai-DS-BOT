"""
cogs/leveling/_portafoglio.py
=============================
Il saldo come immagine (`/monete balance immagine:sì`, ECO-017, D137). Il controllo del modulo lo fa il comando.
Funzioni coperte: ECO-017
"""

from __future__ import annotations

import io
import logging

import discord

from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.rischio_repo import rischio_repo
from core.safe_image import SandboxNonDisponibile, run_image_task
from core.wallet_card import render_wallet_card

logger = logging.getLogger("iyokai.portafoglio")


async def invia_portafoglio(interaction: discord.Interaction, target: discord.abc.User) -> None:
    """Disegna la carta del portafoglio di `target` e la manda come risposta."""
    await interaction.response.defer()
    g, u = interaction.guild.id, target.id
    totali = await leveling_repo.get_totals(g, u)
    banca = (await rischio_repo.banca(g, u)).banca
    posizione = await leveling_repo.get_coins_position(g, u)
    moneta = (await leveling_settings_repo.get_config(g)).impostazioni.currency_name
    immagine = await leveling_settings_repo.get_immagine_moneta(g)
    try:
        png = await run_image_task(render_wallet_card, target.display_name, totali.coins_total, banca, posizione, moneta, immagine)
    except (SandboxNonDisponibile, Exception):
        logger.warning("Portafoglio non disegnato", exc_info=True)
        await interaction.followup.send(f"**{totali.coins_total}** {moneta} · banca **{banca}**")
        return
    await interaction.followup.send(file=discord.File(io.BytesIO(png), filename="portafoglio.png"))
