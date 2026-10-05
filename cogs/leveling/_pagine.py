"""
cogs/leveling/_pagine.py
========================
Liste lunghe mostrate a pagine in un embed, con i bottoni per
sfogliare. Serve alle liste che crescono con i dati (negozio, ruoli
premio, membri di una gilda), che altrimenti supererebbero i 4096
caratteri della descrizione di un embed (LIM-18).
Funzioni coperte: SPEC §15.4, §15.13, §15.14
"""

from __future__ import annotations

import discord

from core.ui_base import BaseView

RIGHE_PER_PAGINA = 10
# Sotto il limite di Discord (4096) con un po' di margine.
LIMITE_CARATTERI_PAGINA = 4000
LIMITE_TITOLO = 256
SECONDI_DI_VITA = 180


def taglia(testo: str, limite: int) -> str:
    """Taglia un testo al limite dato, con i puntini se è stato accorciato."""
    if len(testo) <= limite:
        return testo
    return testo[: limite - 1] + "…"


def dividi_in_pagine(righe: list[str], per_pagina: int = RIGHE_PER_PAGINA) -> list[str]:
    """
    Raggruppa le righe in pagine di testo: al massimo `per_pagina` righe
    e mai oltre LIMITE_CARATTERI_PAGINA caratteri. Una riga troppo lunga
    viene tagliata.
    """
    pagine: list[str] = []
    corrente: list[str] = []
    lunghezza = 0
    for riga in righe:
        riga = taglia(riga, LIMITE_CARATTERI_PAGINA)
        piena = len(corrente) >= per_pagina
        troppo_lunga = lunghezza + len(riga) + 1 > LIMITE_CARATTERI_PAGINA
        if corrente and (piena or troppo_lunga):
            pagine.append("\n".join(corrente))
            corrente, lunghezza = [], 0
        corrente.append(riga)
        lunghezza += len(riga) + 1
    if corrente:
        pagine.append("\n".join(corrente))
    return pagine


class PagineView(BaseView):
    """
    Bottoni ◀ ▶ per sfogliare. Non è persistente: dopo qualche minuto o
    dopo un riavvio i bottoni smettono di rispondere, e basta rilanciare
    il comando. Sfoglia solo chi ha usato il comando.
    """

    def __init__(
        self, titolo: str, pagine: list[str], colore: discord.Color, autore_id: int
    ) -> None:
        super().__init__(timeout=SECONDI_DI_VITA)
        self.titolo = taglia(titolo, LIMITE_TITOLO)
        self.pagine = pagine
        self.colore = colore
        self.autore_id = autore_id
        self.indice = 0
        self._aggiorna_bottoni()

    def embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.titolo, description=self.pagine[self.indice], color=self.colore
        )
        if len(self.pagine) > 1:
            embed.set_footer(text=f"Pagina {self.indice + 1}/{len(self.pagine)}")
        return embed

    def _aggiorna_bottoni(self) -> None:
        self.indietro.disabled = self.indice == 0
        self.avanti.disabled = self.indice >= len(self.pagine) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(
                "Solo chi ha usato il comando può sfogliare queste pagine.", ephemeral=True
            )
            return False
        return True

    async def _vai_a(self, interaction: discord.Interaction, indice: int) -> None:
        self.indice = max(0, min(indice, len(self.pagine) - 1))
        self._aggiorna_bottoni()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def indietro(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vai_a(interaction, self.indice - 1)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def avanti(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vai_a(interaction, self.indice + 1)


async def invia_lista(
    interaction: discord.Interaction,
    titolo: str,
    righe: list[str],
    colore: discord.Color,
    *,
    ephemeral: bool = False,
    per_pagina: int = RIGHE_PER_PAGINA,
) -> None:
    """Risponde con la lista: un embed solo, o più pagine con i bottoni."""
    pagine = dividi_in_pagine(righe, per_pagina)
    view = PagineView(titolo, pagine, colore, interaction.user.id)
    if len(pagine) == 1:
        view.stop()
        await interaction.response.send_message(embed=view.embed(), ephemeral=ephemeral)
        return
    await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=ephemeral)
