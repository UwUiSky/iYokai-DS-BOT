"""
cogs/utility/_owner_pagine.py
=================================
Risposte a pagine per i comandi dell'owner (M 10.12, LIM-22): un elenco
che cresce non deve superare i limiti di Discord. Riusa le pagine e i
bottoni di `cogs/leveling/_pagine.py` (sfoglia solo chi ha lanciato il
comando, cioè l'owner). Il nome comincia con "_": non è un cog.
"""

from __future__ import annotations

from typing import Sequence

import discord

from cogs.leveling._pagine import PagineView, dividi_in_pagine

RIGHE_PER_PAGINA_OWNER = 20


async def invia_a_pagine(
    interaction: discord.Interaction,
    titolo: str,
    righe: Sequence[str],
    *,
    dopo_defer: bool = False,
) -> None:
    """
    Invia `righe` (effimero): un embed solo, o più pagine con ◀ ▶.
    `dopo_defer=True` quando il comando ha già fatto `defer()`.
    """
    pagine = dividi_in_pagine(list(righe), RIGHE_PER_PAGINA_OWNER) or [""]
    vista = PagineView(titolo, pagine, discord.Color.blurple(), interaction.user.id)
    invio = interaction.followup.send if dopo_defer else interaction.response.send_message
    if len(pagine) == 1:
        vista.stop()
        await invio(embed=vista.embed(), ephemeral=True)
        return
    await invio(embed=vista.embed(), view=vista, ephemeral=True)
