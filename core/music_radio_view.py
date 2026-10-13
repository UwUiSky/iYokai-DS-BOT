"""
core/music_radio_view.py
============================
Elenco della playlist della radio a pagine (M 8.15, LIM-21): una
descrizione di embed regge 4096 caratteri, la playlist può avere centinaia
di brani. 2 componenti (Precedente / Successiva), in una riga.
"""

from __future__ import annotations

import discord

from core.ui_base import BaseView


def pagina_embed(pagine: list[str], indice: int) -> discord.Embed:
    embed = discord.Embed(
        title="📻 Playlist della radio",
        description=pagine[indice],
        color=discord.Color.blurple(),
    )
    if len(pagine) > 1:
        embed.set_footer(text=f"Pagina {indice + 1}/{len(pagine)}")
    return embed


class RadioListView(BaseView):
    def __init__(self, pagine: list[str], user_id: int) -> None:
        super().__init__(timeout=180)
        self.pagine = pagine
        self.indice = 0
        self.user_id = user_id
        self._aggiorna_bottoni()

    def _aggiorna_bottoni(self) -> None:
        self.precedente.disabled = self.indice <= 0
        self.successiva.disabled = self.indice >= len(self.pagine) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Questo elenco è di chi ha usato il comando.", ephemeral=True
            )
            return False
        return await super().interaction_check(interaction)

    @discord.ui.button(label="Precedente", style=discord.ButtonStyle.secondary)
    async def precedente(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.indice = max(0, self.indice - 1)
        self._aggiorna_bottoni()
        await interaction.response.edit_message(
            embed=pagina_embed(self.pagine, self.indice), view=self
        )

    @discord.ui.button(label="Successiva", style=discord.ButtonStyle.secondary)
    async def successiva(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.indice = min(len(self.pagine) - 1, self.indice + 1)
        self._aggiorna_bottoni()
        await interaction.response.edit_message(
            embed=pagina_embed(self.pagine, self.indice), view=self
        )
