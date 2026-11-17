"""
cogs/utility/copia_sicura.py
============================
Menu del tasto destro «Richiedi copia sicura» (D74, #160): a chi ha «Gestisci messaggi» mostra, solo a lui, le copie
rifatte dalla sandbox degli allegati del messaggio (mai l'originale) e le righe di scheda per il resto. Al massimo
5 allegati e 9,5 MiB di copie, tetto di tempo `sandbox_secondi_giorno` del server, pausa di 10 secondi per utente.
Il video si converte solo nei canali di ticket e ModMail.
Funzioni coperte: SPEC §8.16 (D74, #160)
Dipende da: core/allegati_mostra.py
"""

from __future__ import annotations

import time

import discord
from discord.ext import commands

from core import allegati_mostra
from core.i18n import lingua_interazione, t
from core.repositories.modmail_repo import modmail_repo
from core.repositories.ticket_repo import ticket_repo

NOME_MENU = "Richiedi copia sicura"
PAUSA_SECONDI = 10
MAX_ALLEGATI = 5
_ultima: dict[int, float] = {}  # utente -> istante dell'ultima richiesta


async def _e_canale_conversazione(channel_id: int) -> bool:
    """Il canale è un ticket o una conversazione ModMail (lì il video si converte)."""
    if await ticket_repo.get_ticket_by_channel(channel_id) is not None:
        return True
    return await modmail_repo.aperta_del_canale(channel_id) is not None


class CopiaSicuraCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._menu = discord.app_commands.ContextMenu(
            name=NOME_MENU, callback=self.menu, allowed_contexts=discord.app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
            allowed_installs=discord.app_commands.AppInstallationType(guild=True, user=False),
        )

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self._menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(NOME_MENU, type=discord.AppCommandType.message)

    async def menu(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        lingua = await lingua_interazione(interaction)
        if interaction.guild is None or not interaction.permissions.manage_messages:
            await interaction.response.send_message(t("copiasicura_permesso", lingua), ephemeral=True)
            return
        if not messaggio.attachments:
            await interaction.response.send_message(t("copiasicura_nessun_allegato", lingua), ephemeral=True)
            return
        adesso = time.monotonic()
        if adesso - _ultima.get(interaction.user.id, -PAUSA_SECONDI) < PAUSA_SECONDI:
            await interaction.response.send_message(t("copiasicura_pausa", lingua, secondi=PAUSA_SECONDI), ephemeral=True)
            return
        _ultima[interaction.user.id] = adesso
        if len(_ultima) > 2000:  # niente crescita senza fine
            for k in [k for k, v in _ultima.items() if adesso - v >= PAUSA_SECONDI]:
                del _ultima[k]
        await interaction.response.defer(ephemeral=True)
        video = await _e_canale_conversazione(interaction.channel_id)
        copie, righe = await allegati_mostra.prepara(
            messaggio.attachments, interaction.guild.id, massimo=MAX_ALLEGATI, con_video=video
        )
        files, _ = allegati_mostra.file_da(copie)
        testo = "\n".join(righe) or t("copiasicura_pronte", lingua, quante=len(copie))
        await interaction.followup.send(
            testo[:2000], files=files, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CopiaSicuraCog(bot))
