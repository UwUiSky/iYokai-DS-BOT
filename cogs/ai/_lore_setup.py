"""
cogs/ai/_lore_setup.py
=====================
Passo «scegli il tema» da offrire alla fine della configurazione guidata: un menu con i temi pronti, saltabile.
Senza scelta vale il tema Yokai. Usa lo stesso punto di `/ai lore`.
Funzioni coperte: SPEC §25.47 (AI-R-052)
"""

from __future__ import annotations

import logging

import discord

from core.ai_impostazioni import imposta_lore
from core.ai_testi_logic import TEMI
from core.repositories.ai_repo import ai_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.ai_lore_setup")

TESTO_PASSO = (
    "Un'ultima cosa: che tema ha il tuo server? Il tema dà il tono ai testi dell'AI e ai giochi "
    "(boss, dungeon, misteri). Puoi saltare: vale il tema Yokai. Lo cambi quando vuoi con `/ai lore`."
)


class _ScegliTema(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Scegli un tema",
            options=[discord.SelectOption(label=nome.capitalize(), value=nome, description=testo[:100]) for nome, testo in TEMI.items()],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        tema = self.values[0]
        await imposta_lore(interaction.guild_id, tema, None, nomi_a_tema=False)
        self.view.stop()
        await interaction.response.edit_message(
            content=f"Tema «{tema}» salvato. Con `/ai lore` puoi aggiungere parole tue o far dare il nome alla moneta.", view=None
        )


class TemaSetupView(BaseView):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.add_item(_ScegliTema())

    @discord.ui.button(label="Salta", style=discord.ButtonStyle.secondary)
    async def salta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="Va bene: resta il tema Yokai.", view=None)


async def proponi_tema(interaction: discord.Interaction) -> bool:
    """Alla fine del wizard: se il server non ha ancora un tema lo propone. Non rompe mai il wizard. True se l'ha mostrato."""
    try:
        if interaction.guild_id is None or (await ai_repo.get_config(interaction.guild_id)).lore_tema:
            return False
        await interaction.followup.send(TESTO_PASSO, view=TemaSetupView(), ephemeral=True)
        return True
    except Exception:
        logger.warning("Passo del tema non mostrato.", exc_info=True)
        return False
