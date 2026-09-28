"""
cogs/utility/setup.py
========================
Il pannello di setup interattivo. Senza questo, ogni modulo scritto
finora (Moderation compreso) resta "pronto ma spento": nessun server
reale ha un modo per accendere `modules.moderation_actions` (o
qualsiasi altro modulo) nel proprio `guild_config`.

Questo comando NON è a sua volta un "modulo" attivabile/disattivabile
— è la dashboard stessa, sempre disponibile (come da schema:
"Setup & Dashboard" è sempre gratuito e non richiede di essere
prima attivato per poter essere usato — sarebbe un problema
dell'uovo e della gallina).

Come funziona
---------------
1. Legge dal PremiumRegistry tutti i moduli registrati finora (ogni
   cog si registra da solo al momento del caricamento — vedi
   core/premium.py e cogs/utility/ping.py per il pattern).
2. Per ognuno, controlla lo stato attuale su questo server
   (db.is_module_active_for_guild).
3. Mostra un menu a tendina multi-selezione con le opzioni già
   pre-selezionate secondo lo stato attuale (SelectOption(default=...)).
4. Al salvataggio, scrive lo stato ESATTO della selezione: un modulo
   che era attivo e non viene riselezionato viene disattivato — non
   basta "selezionare quelli da accendere", la selezione RAPPRESENTA
   lo stato finale desiderato.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import registry, PremiumModule
from core.setup_wizard_logic import is_last_step, next_step, previous_step
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.setup")

# Limite reale di Discord: un Select accetta al massimo 25 opzioni.
# Con più moduli di così servirà paginare il pannello (TODO quando
# il numero di moduli registrati lo richiederà davvero — vedi
# PROGRESS.md).
MAX_SELECT_OPTIONS = 25


class ModuleSelect(discord.ui.Select):
    """
    Il menu a tendina multi-selezione. Le opzioni vengono passate già
    costruite (con `default=True` per i moduli già attivi su questo
    server), così il pannello riflette lo stato reale invece di
    partire sempre vuoto.
    """

    def __init__(self, modules_with_state: list[tuple[PremiumModule, bool]]) -> None:
        options = [
            discord.SelectOption(
                label=module.display_name,
                value=module.name,
                description=module.description[:100],  # limite Discord
                default=is_enabled,
            )
            for module, is_enabled in modules_with_state
        ]
        super().__init__(
            placeholder="Scegli i moduli da attivare su questo server...",
            min_values=0,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        # Non scrive subito sul database: memorizza solo la
        # selezione corrente sulla view, in attesa che l'utente
        # prema "Salva". defer() acknowledges l'interazione senza
        # inviare un nuovo messaggio (il componente Select richiede
        # comunque una risposta, altrimenti Discord mostra
        # "interazione fallita" nel client).
        self.view.selected_values = set(self.values)
        await interaction.response.defer()


class SetupView(BaseView):
    def __init__(
        self, guild_id: int, modules_with_state: list[tuple[PremiumModule, bool]]
    ) -> None:
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.all_module_names = [m.name for m, _ in modules_with_state]
        # Stato iniziale della selezione: quello che risulta già
        # attivo ORA, prima che l'utente tocchi qualsiasi cosa —
        # così se preme subito "Salva" senza modificare nulla, non
        # succede accidentalmente "disattiva tutto".
        self.selected_values: set[str] = {
            m.name for m, is_enabled in modules_with_state if is_enabled
        }
        # Copia CONGELATA dello stato iniziale — self.selected_values
        # viene mutata dal callback della Select man mano che l'utente
        # cambia la selezione, quindi al momento di "Salva" non
        # rifletterebbe più lo stato di partenza. Serve per scrivere
        # nel DB (e quindi nello storico di Config Diff & Rollback,
        # BACKLOG.md §11) solo i moduli il cui stato è DAVVERO
        # cambiato — senza questo, ogni salvataggio registrerebbe una
        # voce di storico "cambiata" per OGNI modulo, anche per quelli
        # rimasti identici, riempiendo lo storico di rumore.
        self._initial_selected_values: frozenset[str] = frozenset(self.selected_values)
        self.message: discord.Message | discord.InteractionMessage | None = None
        self.add_item(ModuleSelect(modules_with_state))

    @discord.ui.button(label="Salva configurazione", style=discord.ButtonStyle.success, row=1)
    async def save(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for module_name in self.all_module_names:
            era_attivo = module_name in self._initial_selected_values
            active = module_name in self.selected_values
            if active == era_attivo:
                continue  # nessun cambiamento reale: non scrivere né loggare nulla
            await db.set_module_active_for_guild(
                self.guild_id, module_name, active, changed_by=interaction.user.id
            )
            # SPEC.md §1.2: emesso SOLO per un cambiamento REALE (mai
            # per un modulo lasciato invariato), stesso identico
            # criterio usato sopra per lo storico Config Diff &
            # Rollback — così i due si allineano sempre. Passa da
            # interaction.client (il Bot vero a runtime) invece di
            # tenere un riferimento al bot sulla view: nessun
            # consumatore lo ascolta ancora (infrastruttura pronta,
            # come invite_tracker prima di Spam Trap — vedi
            # PROGRESS.md), un futuro listener si registra con
            # @commands.Cog.listener() su "on_modules_updated".
            interaction.client.dispatch(
                "modules_updated", self.guild_id, module_name, active, interaction.user.id
            )

        self.stop()
        await interaction.response.edit_message(
            content=(
                f"✅ Configurazione salvata. Moduli attivi: "
                f"{len(self.selected_values)}/{len(self.all_module_names)}."
            ),
            view=None,
        )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.danger, row=1)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.edit_message(
            content="Operazione annullata. Nessuna modifica salvata.", view=None
        )

    async def on_timeout(self) -> None:
        """
        Se l'admin apre il pannello e lo lascia lì senza premere
        nulla, dopo 180 secondi i bottoni vanno disabilitati —
        altrimenti resterebbero cliccabili all'infinito su un
        messaggio "scaduto" agli occhi dell'utente, generando
        confusione se poi qualcun altro ci clicca sopra.
        """
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(
                    content="⏱️ Pannello di setup scaduto. Rilancia /setup per riprovare.",
                    view=self,
                )
            except discord.HTTPException:
                pass  # il messaggio potrebbe essere già stato cancellato


def _wizard_module_names() -> list[str]:
    """
    SPEC.md §2.2: elenco curato di moduli "per iniziare" (non tutti
    quelli registrati — quello è /setup) mostrati uno alla volta dal
    wizard. Import LOCALI, non a livello di modulo — stesso motivo
    già documentato in core/soundboard_log_service.py: evitare
    qualunque rischio di import circolare tra cog diversi, e restare
    caricabile in isolamento nei test.
    """
    from cogs.moderation._shared import MODULE_ACTIONS
    from cogs.automod.automod import MODULE_AUTOMOD
    from cogs.logging.basic_logs import MODULE_LOGGING
    from cogs.utility.greetings import MODULE_GREETINGS
    from cogs.voice_temp.voice_temp import MODULE_VOICE_TEMP
    from cogs.tickets.tickets import MODULE_TICKETS

    return [
        MODULE_ACTIONS,
        MODULE_AUTOMOD,
        MODULE_LOGGING,
        MODULE_GREETINGS,
        MODULE_VOICE_TEMP,
        MODULE_TICKETS,
    ]


class SetupWizardView(BaseView):
    """
    SPEC.md §2.2: a differenza di /setup (tutti i moduli in un solo
    select menu), il wizard mostra un modulo alla volta con Sì/No +
    Avanti/Indietro — pensato per chi preferisce essere guidato passo
    per passo invece di vedere l'intera lista in un colpo.
    """

    def __init__(self, guild_id: int, modules_with_state: list[tuple[PremiumModule, bool]]) -> None:
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.modules_with_state = modules_with_state
        self.selected: dict[str, bool] = {m.name: enabled for m, enabled in modules_with_state}
        self.step = 0
        self.message: discord.Message | discord.InteractionMessage | None = None
        self._sync_buttons()

    def _current_module(self) -> PremiumModule:
        return self.modules_with_state[self.step][0]

    def _render_embed(self) -> discord.Embed:
        module = self._current_module()
        attivo = self.selected[module.name]
        embed = discord.Embed(
            title=f"Passo {self.step + 1}/{len(self.modules_with_state)}: {module.display_name}",
            description=module.description,
            color=discord.Color.green() if attivo else discord.Color.red(),
        )
        embed.set_footer(text=f"Stato attuale: {'ATTIVO' if attivo else 'NON ATTIVO'}")
        return embed

    def _sync_buttons(self) -> None:
        self.previous_button.disabled = self.step == 0
        self.toggle_button.label = "Disattiva" if self.selected[self._current_module().name] else "Attiva"
        self.next_button.label = (
            "Salva" if is_last_step(self.step, len(self.modules_with_state)) else "Avanti"
        )

    @discord.ui.button(label="Indietro", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.step = previous_step(self.step, len(self.modules_with_state))
        self._sync_buttons()
        await interaction.response.edit_message(embed=self._render_embed(), view=self)

    @discord.ui.button(label="Attiva", style=discord.ButtonStyle.primary, row=0)
    async def toggle_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        module = self._current_module()
        self.selected[module.name] = not self.selected[module.name]
        self._sync_buttons()
        await interaction.response.edit_message(embed=self._render_embed(), view=self)

    @discord.ui.button(label="Avanti", style=discord.ButtonStyle.success, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if is_last_step(self.step, len(self.modules_with_state)):
            for module, was_enabled in self.modules_with_state:
                now_enabled = self.selected[module.name]
                if now_enabled != was_enabled:
                    await db.set_module_active_for_guild(
                        self.guild_id, module.name, now_enabled, changed_by=interaction.user.id
                    )
            for child in self.children:
                child.disabled = True
            self.stop()
            await interaction.response.edit_message(
                content="✅ Configurazione guidata completata.", embed=None, view=self
            )
            return

        self.step = next_step(self.step, len(self.modules_with_state))
        self._sync_buttons()
        await interaction.response.edit_message(embed=self._render_embed(), view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(
                    content="⏱️ Wizard scaduto senza salvare. Rilancia /setup-wizard per riprovare.",
                    embed=None,
                    view=self,
                )
            except discord.HTTPException:
                pass


class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="[Admin] Attiva o disattiva i moduli del bot su questo server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        await db.ensure_guild_exists(interaction.guild.id)

        modules = registry.all_modules()
        if not modules:
            await interaction.response.send_message(
                "Nessun modulo risulta ancora registrato. Riprova tra "
                "qualche istante o contatta il supporto se il problema persiste.",
                ephemeral=True,
            )
            return

        if len(modules) > MAX_SELECT_OPTIONS:
            # Fallimento controllato, non un crash: un Select con più
            # di 25 opzioni viene rifiutato da discord.py con un
            # ValueError. Meglio avvisare chiaramente ora che il
            # numero di moduli richiede la paginazione del pannello
            # (vedi PROGRESS.md), piuttosto che rompere il comando
            # in silenzio o mostrare solo i primi 25 senza dirlo.
            logger.warning(
                "Registrati %d moduli, oltre il limite di %d gestibile "
                "da un singolo Select — il pannello /setup necessita "
                "di paginazione, non ancora implementata.",
                len(modules),
                MAX_SELECT_OPTIONS,
            )
            await interaction.response.send_message(
                "Il pannello di setup non può ancora mostrare tutti i "
                "moduli disponibili in una sola schermata (limite "
                "tecnico di Discord). Contatta lo sviluppatore: questa "
                "parte necessita di un aggiornamento.",
                ephemeral=True,
            )
            return

        modules_with_state = [
            (
                module,
                await db.is_module_active_for_guild(interaction.guild.id, module.name),
            )
            for module in modules
        ]

        view = SetupView(interaction.guild.id, modules_with_state)
        await interaction.response.send_message(
            "**Configurazione moduli**\n"
            "Seleziona i moduli da attivare su questo server, poi premi "
            "**Salva configurazione**. I moduli già attivi sono "
            "pre-selezionati.",
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

    @app_commands.command(
        name="setup-wizard",
        description="[Admin] Configura passo-passo i moduli principali del bot.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_wizard(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        await db.ensure_guild_exists(interaction.guild.id)

        modules_with_state: list[tuple[PremiumModule, bool]] = []
        for module_name in _wizard_module_names():
            module = registry.get(module_name)
            if module is None:
                continue  # non ancora registrato: non deve bloccare il resto del wizard
            enabled = await db.is_module_active_for_guild(interaction.guild.id, module_name)
            modules_with_state.append((module, enabled))

        if not modules_with_state:
            await interaction.response.send_message(
                "Nessun modulo disponibile per il wizard al momento. Usa /setup.",
                ephemeral=True,
            )
            return

        view = SetupWizardView(interaction.guild.id, modules_with_state)
        await interaction.response.send_message(embed=view._render_embed(), view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))
