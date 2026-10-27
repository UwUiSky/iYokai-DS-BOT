"""
cogs/utility/_setup_wizard_views.py
===================================
Interfaccia della configurazione guidata (`/admin setup wizard`): un passo per i
ruoli del bot, poi un passo per ogni categoria di moduli. I ruoli si salvano
subito (`imposta_ruolo`, punto unico D16); i moduli alla fine (`imposta_modulo`).
Funzioni coperte: SPEC §2.2, M 10.14 (#66), #148
Dipende da: core/setup_wizard_logic.py

Limiti: menu con al massimo 25 opzioni; tre menu dei ruoli (righe 0-2) più la riga
dei bottoni (riga 4); embed sotto i 4096 caratteri.
"""

from __future__ import annotations

import logging

import discord

from core.command_access import TipoRuolo, imposta_ruolo
from core.config_schema import imposta_modulo
from core.premium import PremiumModule
from core.setup_wizard_logic import (
    TIPO_RUOLI,
    Passo,
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
ETICHETTE_RUOLI = {
    TipoRuolo.ADMIN: "Ruolo admin del bot",
    TipoRuolo.MOD: "Ruolo moderatore del bot",
    TipoRuolo.MODBAN: "Ruolo ban del bot",
}


class SelezioneRuolo(discord.ui.RoleSelect):
    """Scelta di un ruolo del bot: si salva subito, dallo stesso punto del pannello web."""

    def __init__(self, tipo: TipoRuolo, attuale: discord.Role | None, riga: int) -> None:
        super().__init__(
            placeholder=ETICHETTE_RUOLI[tipo],
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

    def __init__(self, passo: Passo, moduli: dict[str, PremiumModule], scelti: dict[str, bool]) -> None:
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
            placeholder="Scegli i moduli da tenere attivi...",
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
        self.message: discord.Message | discord.InteractionMessage | None = None
        self.ricostruisci()

    # ---- disegno ----
    @property
    def passo(self) -> Passo:
        return self.passi[self.step]

    def titolo(self) -> str:
        passo = self.passo
        if passo.tipo == TIPO_RUOLI:
            nome = "Ruoli del bot"
        else:
            nome = self.etichette.get(passo.categoria, passo.categoria)
            if passo.parti > 1:
                nome += f" ({passo.parte}/{passo.parti})"
        return f"Passo {self.step + 1}/{len(self.passi)}: {nome}"

    def embed(self) -> discord.Embed:
        passo = self.passo
        if passo.tipo == TIPO_RUOLI:
            righe = [
                f"**{ETICHETTE_RUOLI[t]}**: {self.ruoli[t].mention if self.ruoli.get(t) else 'non scelto'}"
                for t in ETICHETTE_RUOLI
            ]
            testo = (
                "\n".join(righe)
                + "\n\nChi ha uno di questi ruoli può usare i comandi del livello giusto anche senza "
                "i permessi di Discord. Si salvano subito. Il ruolo admin apre anche i comandi di "
                "sicurezza: lo sceglie solo chi ha «Amministratore»."
            )
        else:
            righe = [
                f"{'✅' if self.scelti[n] else '❌'} **{self.moduli[n].display_name}**"
                f" — {(self.moduli[n].description or '')[:70]}"
                for n in passo.nomi
            ]
            testo = "\n".join(righe)
        embed = discord.Embed(title=self.titolo()[:256], description=testo[:4000])
        embed.set_footer(text="I moduli si salvano con «Salva» all'ultimo passo.")
        return embed

    def ricostruisci(self) -> None:
        self.clear_items()
        passo = self.passo
        if passo.tipo == TIPO_RUOLI:
            for riga, tipo in enumerate(ETICHETTE_RUOLI):
                self.add_item(SelezioneRuolo(tipo, self.ruoli.get(tipo), riga))
        else:
            self.add_item(SelezioneModuli(passo, self.moduli, self.scelti))
            if passo.categoria == CATEGORIA_LOG and passo.parte == 1:
                bottone = discord.ui.Button(
                    label="Crea i canali dei log", style=discord.ButtonStyle.secondary, row=3
                )
                bottone.callback = self._crea_canali_log
                self.add_item(bottone)
        indietro = discord.ui.Button(label="Indietro", row=4, disabled=self.step == 0)
        indietro.callback = self._indietro
        avanti = discord.ui.Button(
            label="Salva" if is_last_step(self.step, len(self.passi)) else "Avanti",
            style=discord.ButtonStyle.success, row=4,
        )
        avanti.callback = self._avanti
        annulla = discord.ui.Button(label="Annulla", style=discord.ButtonStyle.danger, row=4)
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
            content=f"✅ Configurazione guidata completata. Moduli cambiati: {len(cambiati)}.",
            embed=None, view=None,
        )

    async def _annulla(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            content="Operazione annullata. I moduli non sono stati cambiati (i ruoli già scelti restano).",
            embed=None, view=None,
        )

    async def _crea_canali_log(self, interaction: discord.Interaction) -> None:
        """Offre `/log crea-canali`: stessa funzione del comando, niente copia."""
        cog = interaction.client.get_cog(NOME_COG_LOG)
        if cog is None:
            await interaction.response.send_message(
                "La creazione dei canali dei log non è disponibile ora. Usa `/log crea-canali`.",
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
                    content="⏱️ Wizard scaduto senza salvare i moduli. Rilancia /admin setup wizard per riprovare.",
                    embed=None, view=None,
                )
            except discord.HTTPException:
                pass
