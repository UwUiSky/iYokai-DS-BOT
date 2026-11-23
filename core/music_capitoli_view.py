"""
core/music_capitoli_view.py
===========================
Video lunghi (MUS-017): i due bottoni sotto la proposta «usa l'elenco dei brani» (solo per chi ha messo il video).
Funzioni coperte: SPEC §9 (catalogo MUS-017)
Dipende da: core/ui_base.py
"""

from __future__ import annotations

import logging

import discord

from core.i18n import t
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.music.capitoli")


class CapitoliView(BaseView):
    """`applica()` dà il numero di brani messi in coda al posto del video, o None se il video non c'e' piu'."""

    def __init__(self, utente_id: int, lingua: str, applica) -> None:
        super().__init__(timeout=90)
        self.utente_id, self.lingua, self._applica = utente_id, lingua, applica
        self.messaggio: discord.WebhookMessage | None = None
        self._finito = False
        usa = discord.ui.Button(label=t("music_capitoli_usa", lingua)[:80], style=discord.ButtonStyle.primary)
        intero = discord.ui.Button(label=t("music_capitoli_intero", lingua)[:80], style=discord.ButtonStyle.secondary)
        usa.callback, intero.callback = self._usa, self._intero
        self.add_item(usa)
        self.add_item(intero)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.utente_id:
            await interaction.response.send_message(t("music_capitoli_di_altri", self.lingua), ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    async def _usa(self, interaction: discord.Interaction) -> None:
        if self._finito:
            await interaction.response.defer()
            return
        self._finito = True  # un solo clic vale: niente doppia sostituzione
        await interaction.response.defer()
        try:
            fatti = await self._applica()
        except Exception:
            logger.exception("Sostituzione del video con l'elenco dei brani non riuscita.")
            fatti = None
        chiave = "music_capitoli_fatto" if fatti else "music_capitoli_non_piu"
        await interaction.edit_original_response(content=t(chiave, self.lingua, v1=fatti or 0), view=None)
        self.stop()

    async def _intero(self, interaction: discord.Interaction) -> None:
        self._finito = True
        await interaction.response.edit_message(content=t("music_capitoli_intero_ok", self.lingua), view=None)
        self.stop()

    async def on_timeout(self) -> None:
        self._finito = True
        if self.messaggio is not None:
            try:
                await self.messaggio.edit(content=t("music_capitoli_intero_ok", self.lingua), view=None)
            except (discord.HTTPException, discord.NotFound):
                pass
