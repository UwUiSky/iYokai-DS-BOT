"""
core/ui_base.py
===================
BaseView e BaseModal (SEC-10, anche LC-4): stessa protezione
blacklist di core/blacklist_tree.py ma per bottoni, select e modali —
BlacklistAwareCommandTree copre solo i comandi slash, discord.py
chiama interaction_check() separatamente per ogni componente UI.
Ogni View/Modal del progetto eredita da queste invece che
direttamente da discord.ui.View/discord.ui.Modal.
Funzioni coperte: SPEC §17.4/17.5 (SEC-10)
"""

from __future__ import annotations

import logging

import discord

from core.repositories.blacklist_repo import blacklist_repo

logger = logging.getLogger("iyokai.ui_base")

_MESSAGGIO_ERRORE = "Si è verificato un errore imprevisto. Riprova più tardi."


async def _utente_o_server_in_blacklist(interaction: discord.Interaction) -> bool:
    """
    Vero se l'interazione va rifiutata: utente in blacklist (con
    risposta effimera), o server in blacklist (senza risposta — vedi
    la stessa nota in core/blacklist_tree.py: il bot dovrebbe già
    essere uscito da quel server, questo è solo un secondo livello di
    difesa).
    """
    if await blacklist_repo.is_user_blacklisted(interaction.user.id):
        try:
            await interaction.response.send_message(
                "Sei stato bloccato dall'uso di questo bot.", ephemeral=True
            )
        except discord.HTTPException:
            pass
        return True

    if interaction.guild is not None and await blacklist_repo.is_guild_blacklisted(
        interaction.guild.id
    ):
        return True

    return False


async def _rispondi_con_errore(interaction: discord.Interaction) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(_MESSAGGIO_ERRORE, ephemeral=True)
        else:
            await interaction.response.send_message(_MESSAGGIO_ERRORE, ephemeral=True)
    except discord.HTTPException:
        pass


class BaseView(discord.ui.View):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return not await _utente_o_server_in_blacklist(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item
    ) -> None:
        logger.exception(
            "Errore in un componente UI (%s): %s", type(item).__name__ if item else "?", error
        )
        await _rispondi_con_errore(interaction)


class BaseModal(discord.ui.Modal):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return not await _utente_o_server_in_blacklist(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception("Errore in un modale: %s", error)
        await _rispondi_con_errore(interaction)
