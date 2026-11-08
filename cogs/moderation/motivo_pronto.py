"""
cogs/moderation/motivo_pronto.py
================================
/mod-sanzioni applica: sceglie un motivo pronto, il bot propone sanzione e durata di base (D68) e lo staff può
cambiarle prima di confermare. La sanzione vera la esegue il comando già esistente (warn, timeout, kick, ban),
con tutti i suoi controlli.
Funzioni coperte: D68
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import MODULE_ACTIONS, Reason, completa_motivo, ensure_module_enabled
from core import moderation_motivi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.command_access import Livello, puo_usare
from core.duration_logic import parse_duration
from core.i18n import testo_per
from core.ui_base import BaseModal, BaseView

SECONDI_VISTA = 120
# (azione, chiave del testo) nell'ordine del menu
_AZIONI = (("warn", "motivopronto_az_warn"), ("timeout", "motivopronto_az_timeout"), ("kick", "motivopronto_az_kick"), ("ban", "motivopronto_az_ban"))
AZIONI_DEL_MODBAN = ("kick", "ban")  # il gruppo /mod-ban ha un livello suo (D2): chi ha solo il livello Mod non le dà
_COMANDO = {"warn": ("ModerationActionsCog", "warn"), "timeout": ("ModerationActionsCog", "timeout"), "kick": ("ModerationActionsCog", "kick"), "ban": ("ModerationActionsCog", "ban")}


def _durata_testo(secondi: int) -> str:
    return f"{secondi}s"


class ModuloDurata(BaseModal):
    """Un solo campo: la durata del timeout (es. 30m, 1h, 7d)."""

    def __init__(self, vista: "VistaProposta", titolo: str, campo: str) -> None:
        super().__init__(title=titolo[:45], timeout=SECONDI_VISTA)
        self.vista = vista
        self.durata = discord.ui.TextInput(label=campo[:45], max_length=20, default=moderation_motivi.durata_breve(vista.durata_s) if vista.durata_s else None)
        self.add_item(self.durata)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            secondi = parse_duration(self.durata.value)
        except ValueError as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        if secondi > moderation_motivi.MAX_TIMEOUT_S:
            await interaction.response.send_message(await testo_per(interaction, "motivopronto_durata_troppo_lunga"), ephemeral=True)
            return
        self.vista.durata_s = secondi
        await interaction.response.edit_message(content=await self.vista.testo(interaction), view=self.vista)


class VistaProposta(BaseView):
    """La sanzione proposta con menu per cambiarla, tasto per la durata, Conferma e Annulla."""

    def __init__(
        self, cog, origine: discord.Interaction, membro: discord.Member, motivo: str,
        proposta: moderation_motivi.Proposta, etichette: dict[str, str], puo_modban: bool,
    ) -> None:
        super().__init__(timeout=SECONDI_VISTA)
        self.cog = cog
        self.origine = origine
        self.membro = membro
        self.motivo = motivo
        self.severita = proposta.severita
        self.azione = proposta.azione
        self.durata_s = proposta.durata_s
        self.etichette = etichette
        self.puo_modban = puo_modban
        self._partita = False
        self.menu = discord.ui.Select(
            placeholder=etichette["segnaposto"][:150],
            options=[
                discord.SelectOption(label=etichette[a][:100], value=a, default=a == self.azione)
                for a, _ in _AZIONI
                if puo_modban or a not in AZIONI_DEL_MODBAN
            ],
            row=0,
        )
        self.menu.callback = self._cambia_azione
        self.add_item(self.menu)
        self.bottone_durata.label = etichette["durata"][:45]
        self.conferma.label = etichette["conferma"][:45]
        self.annulla.label = etichette["annulla"][:45]
        self._aggiorna_bottoni()

    def _aggiorna_bottoni(self) -> None:
        self.bottone_durata.disabled = self.azione != "timeout"
        for opzione in self.menu.options:
            opzione.default = opzione.value == self.azione

    async def testo(self, interaction: discord.Interaction) -> str:
        sanzione = self.etichette[self.azione]
        if self.azione == "timeout":
            sanzione += f" {moderation_motivi.durata_breve(self.durata_s)}" if self.durata_s else ""
        return await testo_per(
            interaction, "motivopronto_proposta", membro=self.membro.mention, sanzione=sanzione, severita=self.severita or "-"
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.origine.user.id:
            await interaction.response.send_message(await testo_per(interaction, "motivopronto_solo_autore"), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.stop()

    async def _cambia_azione(self, interaction: discord.Interaction) -> None:
        self.azione = self.menu.values[0]
        if self.azione != "timeout":
            self.durata_s = None
        elif self.durata_s is None:
            self.durata_s = 3600
        self._aggiorna_bottoni()
        await interaction.response.edit_message(content=await self.testo(interaction), view=self)

    @discord.ui.button(label="Durata", style=discord.ButtonStyle.secondary, row=1)
    async def bottone_durata(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ModuloDurata(self, self.etichette["durata_titolo"], self.etichette["durata_campo"]))

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger, row=1)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._partita:  # un doppio clic non deve ripetere la sanzione
            return
        if self.azione in AZIONI_DEL_MODBAN and not await puo_usare(interaction, Livello.MODBAN):
            await interaction.response.send_message(await testo_per(interaction, "motivopronto_serve_modban"), ephemeral=True)
            return
        self._partita = True
        self.stop()
        nome_cog, nome_comando = _COMANDO[self.azione]
        cog = interaction.client.get_cog(nome_cog)
        comando = getattr(cog, nome_comando)
        argomenti = {"member": self.membro, "reason": self.motivo}
        if self.azione == "timeout":
            argomenti["duration"] = _durata_testo(self.durata_s or 3600)
        await comando.callback(cog, interaction, **argomenti)
        try:
            await self.origine.edit_original_response(content=await testo_per(self.origine, "motivopronto_fatto"), view=None)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary, row=1)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "motivopronto_annullato"), view=None)


class ModerationMotivoProntoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("mod-sanzioni", nome="applica", descrizione="Dà la sanzione di un motivo pronto, che puoi cambiare prima di confermare.")
    @app_commands.describe(membro="Il membro da sanzionare", motivo="Un motivo pronto del server (scegli dal completamento)")
    @app_commands.autocomplete(motivo=completa_motivo)
    async def applica(self, interaction: discord.Interaction, membro: discord.Member, motivo: Reason) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        proposta = await moderation_motivi.proposta(interaction.guild.id, motivo)
        if proposta is None:
            await interaction.response.send_message(await testo_per(interaction, "motivopronto_senza_sanzione"), ephemeral=True)
            return
        puo_modban = await puo_usare(interaction, Livello.MODBAN)
        if proposta.azione in AZIONI_DEL_MODBAN and not puo_modban:
            await interaction.response.send_message(await testo_per(interaction, "motivopronto_serve_modban"), ephemeral=True)
            return
        testo = await moderation_motivi.espandi(interaction.guild.id, motivo)
        etichette = {chiave_azione: await testo_per(interaction, chiave) for chiave_azione, chiave in _AZIONI}
        for nome, chiave in (
            ("segnaposto", "motivopronto_segnaposto"), ("durata", "motivopronto_durata"), ("conferma", "motivopronto_conferma"),
            ("annulla", "motivopronto_annulla"), ("durata_titolo", "motivopronto_durata_titolo"), ("durata_campo", "motivopronto_durata_campo"),
        ):
            etichette[nome] = await testo_per(interaction, chiave)
        vista = VistaProposta(self, interaction, membro, testo, proposta, etichette, puo_modban)
        await interaction.response.send_message(await vista.testo(interaction), view=vista, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationMotivoProntoCog(bot))
