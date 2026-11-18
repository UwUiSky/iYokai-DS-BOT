"""
cogs/voice_temp/_pannello.py
============================
Il pannello dei vocali temporanei (VOC-009): un messaggio nel canale con i bottoni per rinominare, cambiare il
limite, bloccare, nascondere, espellere e cedere il canale, senza scrivere comandi (comodo anche da telefono).
La vista è persistente (custom_id fissi, `bot.add_view` all'avvio): ogni clic passa dagli stessi comandi di
`/voice`, che controllano a OGNI azione che chi clicca sia il proprietario del canale in cui si trova.
Funzioni coperte: SPEC §12 (#127 VOC-009)
"""

from __future__ import annotations

import discord

from core.i18n import testo_per
from core.ui_base import BaseView

NOME_COG = "VoiceTempCog"
MAX_NOME = 100


def _cog(interaction: discord.Interaction):
    return interaction.client.get_cog(NOME_COG)


async def _no_cog(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(await testo_per(interaction, "voicepanel_non_disponibile"), ephemeral=True)


class _FinestraNome(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="Nuovo nome del canale", timeout=300)
        self.nome = discord.ui.TextInput(label="Nome", min_length=1, max_length=MAX_NOME)
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog = _cog(interaction)
        if cog is None:
            return await _no_cog(interaction)
        await cog.rename.callback(cog, interaction, str(self.nome.value).strip()[:MAX_NOME] or "canale")


class _FinestraLimite(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="Limite di utenti", timeout=300)
        self.limite = discord.ui.TextInput(label="Numero da 0 a 99 (0 = nessun limite)", min_length=1, max_length=2)
        self.add_item(self.limite)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog = _cog(interaction)
        if cog is None:
            return await _no_cog(interaction)
        testo = str(self.limite.value).strip()
        if not testo.isdigit():
            return await interaction.response.send_message(await testo_per(interaction, "voicepanel_numero_non_valido"), ephemeral=True)
        await cog.limit.callback(cog, interaction, int(testo))


class _SceltaMembro(BaseView):
    """Il menu temporaneo per scegliere chi espellere o a chi cedere il canale; lo vede e lo usa solo chi l'ha aperto."""

    def __init__(self, autore_id: int, azione: str) -> None:
        super().__init__(timeout=60)
        self.autore_id, self.azione = autore_id, azione
        scelta = discord.ui.UserSelect(placeholder="Scegli un utente", min_values=1, max_values=1)
        scelta.callback = self._scelto
        self.add_item(scelta)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(await testo_per(interaction, "alertgest_solo_chi_ha_lanciato"), ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    async def _scelto(self, interaction: discord.Interaction) -> None:
        cog = _cog(interaction)
        if cog is None:
            return await _no_cog(interaction)
        membro = interaction.guild.get_member(int(interaction.data["values"][0])) if interaction.guild else None
        if membro is None:
            return await interaction.response.send_message(await testo_per(interaction, "voicepanel_utente_non_nel_server"), ephemeral=True)
        self.stop()
        comando = cog.kick if self.azione == "espelli" else cog.transfer
        await comando.callback(cog, interaction, membro)


class PannelloVocaleView(BaseView):
    """I bottoni del pannello (VOC-009). Nessun dato nella vista: il canale è quello di chi clicca."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _comando(self, interaction: discord.Interaction, nome: str, *argomenti) -> None:
        cog = _cog(interaction)
        if cog is None:
            return await _no_cog(interaction)
        await getattr(cog, nome).callback(cog, interaction, *argomenti)

    @discord.ui.button(label="Rinomina", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="iyokai_voice_panel_rename", row=0)
    async def rinomina(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(_FinestraNome())

    @discord.ui.button(label="Limite", emoji="👥", style=discord.ButtonStyle.secondary, custom_id="iyokai_voice_panel_limit", row=0)
    async def limite(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(_FinestraLimite())

    @discord.ui.button(label="Blocca", emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="iyokai_voice_panel_lock", row=0)
    async def blocca(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._comando(interaction, "lock")

    @discord.ui.button(label="Sblocca", emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="iyokai_voice_panel_unlock", row=0)
    async def sblocca(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._comando(interaction, "unlock")

    @discord.ui.button(label="Nascondi", emoji="🙈", style=discord.ButtonStyle.secondary, custom_id="iyokai_voice_panel_hide", row=1)
    async def nascondi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._comando(interaction, "nascondi", True)

    @discord.ui.button(label="Mostra", emoji="👁️", style=discord.ButtonStyle.secondary, custom_id="iyokai_voice_panel_show", row=1)
    async def mostra(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._comando(interaction, "nascondi", False)

    @discord.ui.button(label="Espelli", emoji="🚪", style=discord.ButtonStyle.danger, custom_id="iyokai_voice_panel_kick", row=1)
    async def espelli(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(await testo_per(interaction, "voicepanel_scegli"), view=_SceltaMembro(interaction.user.id, "espelli"), ephemeral=True)

    @discord.ui.button(label="Cedi", emoji="👑", style=discord.ButtonStyle.secondary, custom_id="iyokai_voice_panel_transfer", row=1)
    async def cedi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(await testo_per(interaction, "voicepanel_scegli"), view=_SceltaMembro(interaction.user.id, "cedi"), ephemeral=True)
