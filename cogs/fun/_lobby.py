"""
cogs/fun/_lobby.py
==================
Sala d'attesa dei giochi di gruppo (#131, D70, B7 e B8): bottoni Entra, Esci e Avvia (solo chi ha dato il comando),
da 1 a 10 giocatori. L'elenco si aggiorna a ogni clic; allo scadere il gioco parte se i giocatori bastano.
Funzioni coperte: SPEC §16 (FUN-007, 010, 011)
"""

from __future__ import annotations

import asyncio

import discord

from core.i18n import testo_per
from core.ui_base import BaseView

NESSUNA_MENZIONE = discord.AllowedMentions.none()


class VistaLobby(BaseView):
    def __init__(self, host_id: int, minimo: int, massimo: int, intestazione: str, etichette: tuple[str, str, str], secondi: int = 45) -> None:
        super().__init__(timeout=secondi)
        self.giocatori: list[int] = [host_id]
        self.host_id, self.minimo, self.massimo, self.intestazione = host_id, minimo, massimo, intestazione
        self.pronta = asyncio.Event()
        self.avviata = False
        self.entra.label, self.esci.label, self.avvia.label = (e[:45] for e in etichette)

    async def testo(self, interaction: discord.Interaction) -> str:
        elenco = " ".join(f"<@{u}>" for u in self.giocatori)
        corpo = await testo_per(interaction, "gioco_lobby_giocatori", pubblica=True, n=len(self.giocatori), massimo=self.massimo, elenco=elenco)
        return f"{self.intestazione}\n{corpo}"[:2000]

    async def _aggiorna(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content=await self.testo(interaction), view=self, allowed_mentions=NESSUNA_MENZIONE)

    @discord.ui.button(style=discord.ButtonStyle.success)
    async def entra(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id in self.giocatori:
            await interaction.response.send_message(await testo_per(interaction, "gioco_lobby_gia"), ephemeral=True)
        elif len(self.giocatori) >= self.massimo:
            await interaction.response.send_message(await testo_per(interaction, "gioco_lobby_pieno"), ephemeral=True)
        else:
            self.giocatori.append(interaction.user.id)  # prima di ogni await
            await self._aggiorna(interaction)

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def esci(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id == self.host_id:
            await interaction.response.send_message(await testo_per(interaction, "gioco_lobby_host_resta"), ephemeral=True)
        elif interaction.user.id in self.giocatori:
            self.giocatori.remove(interaction.user.id)
            await self._aggiorna(interaction)
        else:
            await interaction.response.send_message(await testo_per(interaction, "gioco_lobby_non_dentro"), ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.primary)
    async def avvia(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.host_id:
            await interaction.response.send_message(await testo_per(interaction, "gioco_lobby_solo_host"), ephemeral=True)
        elif len(self.giocatori) < self.minimo:
            await interaction.response.send_message(await testo_per(interaction, "gioco_lobby_pochi", minimo=self.minimo), ephemeral=True)
        elif not self.avviata:
            self.avviata = True
            self.stop()
            self.pronta.set()
            await interaction.response.edit_message(view=None)

    async def on_timeout(self) -> None:
        if not self.avviata and len(self.giocatori) >= self.minimo:
            self.avviata = True
        self.pronta.set()
