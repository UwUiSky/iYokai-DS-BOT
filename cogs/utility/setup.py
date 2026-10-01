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
3. Con `categoria` mostra un menu a tendina multi-selezione dei soli
   moduli di quella categoria, con le opzioni già pre-selezionate
   secondo lo stato attuale (SelectOption(default=...)). Senza
   `categoria` mostra un elenco di sola lettura di tutti i moduli.
4. Al salvataggio, scrive lo stato ESATTO della selezione: un modulo
   che era attivo e non viene riselezionato viene disattivato — non
   basta "selezionare quelli da accendere", la selezione RAPPRESENTA
   lo stato finale desiderato.
Funzioni coperte: SPEC §2.1, §2.2, REVIEW.md BUG-2 (issue #4, #38, #43, #49).
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
# Per questo /setup mostra un Select per categoria (BUG-2).
MAX_SELECT_OPTIONS = 25

# BUG-2: nomi leggibili delle categorie di core.premium.CATEGORIE_MODULI.
ETICHETTE_CATEGORIE = {
    "moderation": "Moderazione",
    "security": "Sicurezza",
    "automod": "AutoMod",
    "logging": "Log",
    "utility": "Utility",
    "tickets": "Ticket",
    "voice": "Vocali",
    "music": "Musica",
    "leveling": "Livelli ed economia",
    "fun": "Fun",
}


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
        description="[Admin] Attiva o disattiva i moduli del bot, per categoria.",
    )
    @app_commands.describe(
        categoria="Categoria da configurare. Senza scelta: elenco di sola lettura."
    )
    @app_commands.choices(
        categoria=[
            app_commands.Choice(name=etichetta, value=valore)
            for valore, etichetta in ETICHETTE_CATEGORIE.items()
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(
        self, interaction: discord.Interaction, categoria: str | None = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        # LC-3: le letture dal database possono superare i 3 secondi.
        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild_exists(interaction.guild.id)

        if categoria is None:
            embed = await self._embed_stato_moduli(interaction.guild.id)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        modules = registry.modules_in_category(categoria)
        if not modules:
            await interaction.followup.send(
                "Nessun modulo risulta registrato in questa categoria.",
                ephemeral=True,
            )
            return

        if len(modules) > MAX_SELECT_OPTIONS:
            # Non succede con le categorie attuali (il test sul registry
            # reale lo verifica); se un giorno accade, avvisa invece di
            # far rifiutare il Select da discord.py.
            logger.warning(
                "Categoria %s con %d moduli, oltre il limite di %d di un Select.",
                categoria,
                len(modules),
                MAX_SELECT_OPTIONS,
            )
            await interaction.followup.send(
                "Questa categoria ha troppi moduli per una sola schermata. "
                "Contatta lo sviluppatore.",
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
        view.message = await interaction.followup.send(
            f"**Configurazione moduli — {ETICHETTE_CATEGORIE[categoria]}**\n"
            "Seleziona i moduli da attivare su questo server, poi premi "
            "**Salva configurazione**. I moduli già attivi sono "
            "pre-selezionati.",
            view=view,
            ephemeral=True,
            wait=True,
        )

    async def _embed_stato_moduli(self, guild_id: int) -> discord.Embed:
        """Elenco di sola lettura: stato di tutti i moduli, per categoria."""
        embed = discord.Embed(
            title="Stato dei moduli",
            description="Scegli una categoria in `/setup categoria:` per modificarla.",
        )
        for valore, etichetta in ETICHETTE_CATEGORIE.items():
            righe = []
            for modulo in registry.modules_in_category(valore):
                attivo = await db.is_module_active_for_guild(guild_id, modulo.name)
                righe.append(f"{'✅' if attivo else '❌'} {modulo.display_name}")
            if righe:
                embed.add_field(name=etichetta, value="\n".join(righe), inline=False)
        return embed

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
