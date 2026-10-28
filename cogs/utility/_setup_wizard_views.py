"""
cogs/utility/_setup_wizard_views.py
===================================
Interfaccia della configurazione guidata (`/admin setup wizard`): un passo per i
ruoli del bot, poi un passo per ogni categoria di moduli. I ruoli si salvano
subito (`imposta_ruolo`, punto unico D16); i moduli alla fine (`imposta_modulo`).
Funzioni coperte: SPEC §2.2, 22.16, M 10.14 (#66), #148
Dipende da: core/setup_wizard_logic.py

Limiti: menu con al massimo 25 opzioni; tre menu dei ruoli (righe 0-2) più la riga
dei bottoni (riga 4); embed sotto i 4096 caratteri.
"""

from __future__ import annotations

import logging

import discord

from core.command_access import TipoRuolo, imposta_ruolo
from core.config_schema import imposta_modulo
from core.i18n import t, testo_per
from core.premium import PremiumModule
from core.setup_wizard_logic import (
    TIPO_RUOLI,
    CanaleWizard,
    Passo,
    canale_per_passo,
    is_last_step,
    moduli_da_scrivere,
    next_step,
    previous_step,
)
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.setup")

TIMEOUT = 300
CATEGORIA_LOG = "logging"
NOME_COG_LOG = "LogConfigCog"
TESTI_RUOLI = {
    TipoRuolo.ADMIN: "setup_ruolo_admin",
    TipoRuolo.MOD: "setup_ruolo_mod",
    TipoRuolo.MODBAN: "setup_ruolo_modban",
}


class SelezioneRuolo(discord.ui.RoleSelect):
    """Scelta di un ruolo del bot: si salva subito, dallo stesso punto del pannello web."""

    def __init__(self, tipo: TipoRuolo, attuale: discord.Role | None, riga: int, lingua: str = "it") -> None:
        super().__init__(
            placeholder=t(TESTI_RUOLI[tipo], lingua),
            min_values=0,
            max_values=1,
            default_values=[attuale] if attuale is not None else [],
            row=riga,
        )
        self.tipo = tipo

    async def callback(self, interaction: discord.Interaction) -> None:
        vista = self.view  # ricostruisci() stacca questo menu dalla vista
        ruolo = self.values[0] if self.values else None
        guild = interaction.guild
        try:
            await imposta_ruolo(
                guild, self.tipo, guild.get_role(ruolo.id) if ruolo else None,
                interaction.user.id,
                autore=interaction.user if isinstance(interaction.user, discord.Member) else None,
            )
        except ValueError as errore:  # ruolo non valido o admin senza «Amministratore»
            vista.ricostruisci()
            await interaction.response.edit_message(embed=vista.embed(), view=vista)
            await interaction.followup.send(str(errore), ephemeral=True)
            return
        vista.ruoli[self.tipo] = guild.get_role(ruolo.id) if ruolo else None
        vista.ricostruisci()
        await interaction.response.edit_message(embed=vista.embed(), view=vista)


class SelezioneModuli(discord.ui.Select):
    """I moduli di un passo: la scelta resta nella vista fino a «Salva»."""

    def __init__(
        self, passo: Passo, moduli: dict[str, PremiumModule], scelti: dict[str, bool], lingua: str = "it"
    ) -> None:
        opzioni = [
            discord.SelectOption(
                label=moduli[n].display_name[:100],
                value=n,
                description=(moduli[n].description or "")[:100] or None,
                default=scelti[n],
            )
            for n in passo.nomi
        ]
        super().__init__(
            placeholder=t("setup_wizard_scegli_moduli", lingua),
            min_values=0,
            max_values=len(opzioni),
            options=opzioni,
            row=0,
        )
        self.passo = passo

    async def callback(self, interaction: discord.Interaction) -> None:
        vista = self.view  # ricostruisci() stacca questo menu dalla vista
        for nome in self.passo.nomi:
            vista.scelti[nome] = nome in self.values
        vista.ricostruisci()
        await interaction.response.edit_message(embed=vista.embed(), view=vista)


class SetupWizardView(BaseView):
    """Il wizard: Indietro / Avanti (Salva all'ultimo passo) / Annulla."""

    def __init__(
        self,
        guild_id: int,
        passi: list[Passo],
        moduli: dict[str, PremiumModule],
        stato: dict[str, bool],
        ruoli: dict[TipoRuolo, discord.Role | None],
        etichette: dict[str, str],
    ) -> None:
        super().__init__(timeout=TIMEOUT)
        self.guild_id = guild_id
        self.passi = passi
        self.moduli = moduli
        self.iniziale = dict(stato)
        self.scelti = dict(stato)
        self.ruoli = dict(ruoli)
        self.etichette = etichette
        self.step = 0
        self.lingua = "it"  # la imposta il comando prima di mandare il wizard
        self.message: discord.Message | discord.InteractionMessage | None = None
        self.ricostruisci()

    # ---- disegno ----
    @property
    def passo(self) -> Passo:
        return self.passi[self.step]

    def titolo(self) -> str:
        passo = self.passo
        if passo.tipo == TIPO_RUOLI:
            nome = t("setup_wizard_passo_ruoli", self.lingua)
        else:
            nome = self.etichette.get(passo.categoria, passo.categoria)
            if passo.parti > 1:
                nome += f" ({passo.parte}/{passo.parti})"
        return t("setup_wizard_passo", self.lingua, n=self.step + 1, totale=len(self.passi), nome=nome)

    def embed(self) -> discord.Embed:
        passo = self.passo
        if passo.tipo == TIPO_RUOLI:
            righe = [
                f"**{t(TESTI_RUOLI[tipo], self.lingua)}**: "
                f"{self.ruoli[tipo].mention if self.ruoli.get(tipo) else t('setup_wizard_non_scelto', self.lingua)}"
                for tipo in TESTI_RUOLI
            ]
            testo = "\n".join(righe) + "\n\n" + t("setup_wizard_ruoli_testo", self.lingua)
        else:
            righe = [
                f"{'✅' if self.scelti[n] else '❌'} **{self.moduli[n].display_name}**"
                f" — {(self.moduli[n].description or '')[:70]}"
                for n in passo.nomi
            ]
            testo = "\n".join(righe)
        embed = discord.Embed(title=self.titolo()[:256], description=testo[:4000])
        embed.set_footer(text=t("setup_wizard_footer", self.lingua))
        return embed

    def ricostruisci(self) -> None:
        self.clear_items()
        passo = self.passo
        if passo.tipo == TIPO_RUOLI:
            for riga, tipo in enumerate(TESTI_RUOLI):
                self.add_item(SelezioneRuolo(tipo, self.ruoli.get(tipo), riga, self.lingua))
        else:
            self.add_item(SelezioneModuli(passo, self.moduli, self.scelti, self.lingua))
            if canale_per_passo(passo) is not None:
                bottone = discord.ui.Button(
                    label=t("setup_wizard_crea_canale", self.lingua, nome=canale_per_passo(passo).nome),
                    style=discord.ButtonStyle.secondary, row=3,
                )
                bottone.callback = self._crea_canale
                self.add_item(bottone)
            if passo.categoria == CATEGORIA_LOG and passo.parte == 1:
                bottone = discord.ui.Button(
                    label=t("setup_wizard_crea_log", self.lingua), style=discord.ButtonStyle.secondary, row=3
                )
                bottone.callback = self._crea_canali_log
                self.add_item(bottone)
        indietro = discord.ui.Button(label=t("setup_wizard_indietro", self.lingua), row=4, disabled=self.step == 0)
        indietro.callback = self._indietro
        avanti = discord.ui.Button(
            label=t("setup_wizard_salva" if is_last_step(self.step, len(self.passi)) else "setup_wizard_avanti", self.lingua),
            style=discord.ButtonStyle.success, row=4,
        )
        avanti.callback = self._avanti
        annulla = discord.ui.Button(label=t("setup_wizard_annulla", self.lingua), style=discord.ButtonStyle.danger, row=4)
        annulla.callback = self._annulla
        for bottone in (indietro, avanti, annulla):
            self.add_item(bottone)

    # ---- bottoni ----
    async def _indietro(self, interaction: discord.Interaction) -> None:
        self.step = previous_step(self.step, len(self.passi))
        self.ricostruisci()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _avanti(self, interaction: discord.Interaction) -> None:
        if not is_last_step(self.step, len(self.passi)):
            self.step = next_step(self.step, len(self.passi))
            self.ricostruisci()
            await interaction.response.edit_message(embed=self.embed(), view=self)
            return
        cambiati = moduli_da_scrivere(self.iniziale, self.scelti)
        for nome, attivo in cambiati:
            # M 10.13 e D16: stesso punto unico di /admin setup attiva e del pannello.
            await imposta_modulo(interaction.client, self.guild_id, nome, attivo, interaction.user.id)
        self.stop()
        await interaction.response.edit_message(
            content=await testo_per(interaction, "setup_wizard_fatto", cambiati=len(cambiati)),
            embed=None, view=None,
        )

    async def _annulla(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=await testo_per(interaction, "setup_wizard_annullato"),
            embed=None, view=None,
        )

    async def _crea_canale(self, interaction: discord.Interaction) -> None:
        """22.16: crea il canale della categoria e lo collega con lo stesso punto dei comandi."""
        canale = canale_per_passo(self.passo)
        if canale is None:
            return
        await interaction.response.defer(ephemeral=True)
        testo = await crea_e_collega(interaction, canale)
        await interaction.followup.send(testo, ephemeral=True)

    async def _crea_canali_log(self, interaction: discord.Interaction) -> None:
        """Offre `/log crea-canali`: stessa funzione del comando, niente copia."""
        cog = interaction.client.get_cog(NOME_COG_LOG)
        if cog is None:
            await interaction.response.send_message(
                await testo_per(interaction, "setup_wizard_log_non_disponibile"),
                ephemeral=True,
            )
            return
        await cog.crea_canali.callback(cog, interaction)

    async def on_timeout(self) -> None:
        for figlio in self.children:
            figlio.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(
                    content=t("setup_wizard_scaduto", self.lingua),
                    embed=None, view=None,
                )
            except discord.HTTPException:
                pass


async def crea_e_collega(interaction: discord.Interaction, canale: CanaleWizard) -> str:
    """
    Crea il canale di testo e lo imposta dove lo usa la funzione (mod-log, allarmi,
    benvenuto). Restituisce il testo da dire a chi ha premuto. Non accende i moduli.
    """
    # Import qui: i comandi dei log e dei messaggi di benvenuto non sono dipendenze del wizard.
    from cogs.logging.log_config import MAX_CANALI_SERVER, _riservato, permessi_mancanti
    from cogs.moderation._shared import SETTING_MOD_LOG_CHANNEL
    from core import channel_router as router
    from core.database import db
    from core.repositories.greetings_repo import greetings_repo

    guild = interaction.guild
    mancano = permessi_mancanti(guild.me.guild_permissions, ("manage_channels", "view_channel", "send_messages"))
    if mancano:
        return await testo_per(interaction, "setup_wizard_canale_permessi", permessi=", ".join(mancano))
    if len(guild.channels) + 1 > MAX_CANALI_SERVER:
        return await testo_per(interaction, "setup_wizard_canale_pieno", massimo=MAX_CANALI_SERVER)
    try:
        nuovo = await guild.create_text_channel(
            canale.nome,
            overwrites=_riservato(guild) if canale.riservato else {},
            topic=canale.argomento[:1024],
            reason="/admin setup wizard",
        )
    except discord.HTTPException as errore:
        logger.warning("wizard: canale %s non creato (server %s): %s", canale.chiave, guild.id, errore)
        return await testo_per(interaction, "setup_wizard_canale_errore")
    if canale.chiave == "mod-log":
        await db.set_guild_setting(guild.id, SETTING_MOD_LOG_CHANNEL, nuovo.id)
    elif canale.chiave == "allarmi":
        await router.output_channel_repo.imposta(guild.id, router.TIPO_ALLARMI, nuovo.id)
    else:
        config = await greetings_repo.get_config(guild.id)
        await greetings_repo.set_welcome(
            guild.id, enabled=config.welcome_enabled, channel_id=nuovo.id, message=config.welcome_message,
            dm=config.welcome_dm, ping_ruoli=config.welcome_ping_ruoli,
        )
    return await testo_per(interaction, "setup_wizard_canale_creato", canale=nuovo.mention)
