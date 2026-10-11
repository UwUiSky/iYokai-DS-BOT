"""
cogs/utility/_owner_pagine.py
=================================
Risposte a pagine per i comandi dell'owner (M 10.12, LIM-22): un elenco
che cresce non deve superare i 2000 caratteri di un messaggio. Più di una
pagina = messaggio con i bottoni Indietro / Avanti. Il nome comincia con
"_" perché è solo UI, non un cog.
"""

from __future__ import annotations

from typing import Sequence

import discord

from core.config import config
from core.lista_limiti_logic import dividi_in_pagine
from core.ui_base import BaseView

# Il messaggio porta in coda "Pagina i/n": si lascia spazio.
LIMITE_PAGINA = 1900


class PagineView(BaseView):
    def __init__(self, pagine: list[str], *, timeout: float = 180) -> None:
        super().__init__(timeout=timeout)
        self.pagine = pagine
        self.indice = 0
        self._aggiorna_bottoni()

    def testo_pagina(self) -> str:
        return f"{self.pagine[self.indice]}\n\nPagina {self.indice + 1}/{len(self.pagine)}"

    def _aggiorna_bottoni(self) -> None:
        self.indietro.disabled = self.indice == 0
        self.avanti.disabled = self.indice >= len(self.pagine) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return False
        return await super().interaction_check(interaction)

    @discord.ui.button(label="Indietro", style=discord.ButtonStyle.secondary)
    async def indietro(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.indice = max(0, self.indice - 1)
        self._aggiorna_bottoni()
        await interaction.response.edit_message(content=self.testo_pagina(), view=self)

    @discord.ui.button(label="Avanti", style=discord.ButtonStyle.secondary)
    async def avanti(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.indice = min(len(self.pagine) - 1, self.indice + 1)
        self._aggiorna_bottoni()
        await interaction.response.edit_message(content=self.testo_pagina(), view=self)


async def invia_a_pagine(
    interaction: discord.Interaction,
    righe: Sequence[str],
    *,
    dopo_defer: bool = False,
) -> None:
    """
    Invia `righe` (effimero) in una pagina sola o, se non basta, con i
    bottoni. `dopo_defer=True` quando il comando ha già fatto `defer()`.
    """
    pagine = dividi_in_pagine(righe, LIMITE_PAGINA)
    if len(pagine) == 1:
        if dopo_defer:
            await interaction.followup.send(pagine[0], ephemeral=True)
        else:
            await interaction.response.send_message(pagine[0], ephemeral=True)
        return
    vista = PagineView(pagine)
    if dopo_defer:
        await interaction.followup.send(vista.testo_pagina(), view=vista, ephemeral=True)
    else:
        await interaction.response.send_message(vista.testo_pagina(), view=vista, ephemeral=True)
