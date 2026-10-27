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
Funzioni coperte: SPEC §2.1, §2.2, M 10.14 (#66), #148, REVIEW.md BUG-2 (issue #4, #38, #43, #49).
Il wizard (`/admin setup wizard`) sta in cogs/utility/_setup_wizard_views.py.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.bot_inviti import altri_bot
from core.config_schema import imposta_modulo
from core.i18n import testo_per
from core.database import db
from core.premium import registry, PremiumModule
from core.command_access import TipoRuolo, leggi_ruolo
from core.setup_wizard_logic import costruisci_passi
from core.ui_base import BaseView

from cogs.utility._setup_wizard_views import SetupWizardView  # noqa: F401  (esportato per i test)

logger = logging.getLogger("iyokai.setup")

# Limite reale di Discord: un Select accetta al massimo 25 opzioni.
# Per questo /admin setup attiva mostra un Select per categoria (BUG-2).
MAX_SELECT_OPTIONS = 25

# BUG-2: nomi leggibili delle categorie di core.premium.CATEGORIE_MODULI.
ETICHETTE_CATEGORIE = {
    "moderation": "Moderazione",
    "security": "Sicurezza",
    "automod": "AutoMod",
    "logging": "Log",
    "utility": "Utility",
    "community": "Community",
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
            # D16: stesso punto unico del pannello web (storico + evento `modules_updated`).
            await imposta_modulo(interaction.client, self.guild_id, module_name, active, interaction.user.id)

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
                    content="⏱️ Pannello di setup scaduto. Rilancia /admin setup attiva per riprovare.",
                    view=self,
                )
            except discord.HTTPException:
                pass  # il messaggio potrebbe essere già stato cancellato


def vista_autorizzazione(guild_id: int, user_id: int):
    """
    #148: bottone-link per far scrivere al bot i permessi dei comandi (OAuth2 dell'admin).
    `MISSING` (nessuna vista) se l'OAuth2 non è configurato: resta la base di sempre.
    """
    from core.command_permissions import link_per_admin

    try:
        url = link_per_admin(guild_id, user_id)
    except Exception:  # chiave non valida: meglio nessun bottone che un errore nel setup
        logger.warning("Link di autorizzazione dei permessi non costruibile.", exc_info=True)
        url = None
    if url is None:
        return discord.utils.MISSING
    vista = BaseView(timeout=180)
    vista.add_item(discord.ui.Button(label="Nascondi i comandi a chi non può usarli (OAuth2)", url=url))
    return vista


class SetupCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin",
        nome="attiva",
        descrizione="Attiva o disattiva i moduli del bot, per categoria.",
        sottogruppo=("setup", "Attivazione dei moduli e configurazione guidata"),
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
            extra = {}
            vista = vista_autorizzazione(interaction.guild.id, interaction.user.id)
            if vista is not discord.utils.MISSING:
                extra["view"] = vista
            testo = await self._testo_altri_bot(interaction)
            if testo:
                extra["content"] = testo
            await interaction.followup.send(embed=embed, ephemeral=True, **extra)
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

    async def _testo_altri_bot(self, interaction: discord.Interaction) -> str:
        """Gli altri bot di iYokai in questo server, con i link di invito e cosa resta ridotto se mancano (#113)."""
        try:
            voci = await altri_bot(self.bot, interaction.guild.id)
        except Exception:  # noqa: BLE001 - un dato in più: se non si legge, il setup funziona lo stesso
            logger.warning("Elenco degli altri bot non disponibile.", exc_info=True)
            return ""
        righe = []
        for voce in voci:
            if not voce.mancanti:
                righe.append(await testo_per(interaction, f"setup_bot_{voce.chiave}_ok", presenti=voce.presenti, totale=voce.totale))
                continue
            elenco = ", ".join(f"[{nome}]({url})" for nome, url in voce.mancanti)
            righe.append(
                await testo_per(interaction, f"setup_bot_{voce.chiave}_manca", presenti=voce.presenti, totale=voce.totale, elenco=elenco)
            )
        if not righe:
            return ""
        return ("**" + await testo_per(interaction, "setup_bot_titolo") + "**\n" + "\n".join(righe))[:2000]

    async def _embed_stato_moduli(self, guild_id: int) -> discord.Embed:
        """Elenco di sola lettura: stato di tutti i moduli, per categoria."""
        embed = discord.Embed(
            title="Stato dei moduli",
            description="Scegli una categoria in `/admin setup attiva categoria:` per modificarla.",
        )
        for valore, etichetta in ETICHETTE_CATEGORIE.items():
            righe = []
            for modulo in registry.modules_in_category(valore):
                attivo = await db.is_module_active_for_guild(guild_id, modulo.name)
                righe.append(f"{'✅' if attivo else '❌'} {modulo.display_name}")
            if righe:
                embed.add_field(name=etichetta, value="\n".join(righe), inline=False)
        return embed

    @comando_di_gruppo(
        "admin",
        nome="wizard",
        descrizione="Configura passo-passo ruoli e moduli del bot, una categoria alla volta.",
        sottogruppo=("setup", "Attivazione dei moduli e configurazione guidata"),
    )
    async def setup_wizard(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        await db.ensure_guild_exists(interaction.guild.id)
        guild = interaction.guild

        per_categoria: dict[str, list[str]] = {}
        moduli: dict[str, PremiumModule] = {}
        stato: dict[str, bool] = {}
        for categoria in ETICHETTE_CATEGORIE:
            for modulo in registry.modules_in_category(categoria):
                per_categoria.setdefault(categoria, []).append(modulo.name)
                moduli[modulo.name] = modulo
                stato[modulo.name] = await db.is_module_active_for_guild(guild.id, modulo.name)
        if not moduli:
            await interaction.response.send_message(
                "Nessun modulo disponibile per il wizard al momento. Usa /admin setup attiva.",
                ephemeral=True,
            )
            return

        passi = costruisci_passi(per_categoria, tuple(ETICHETTE_CATEGORIE))
        ruoli = {}
        for tipo in TipoRuolo:
            ruolo_id = await leggi_ruolo(guild.id, tipo)
            ruoli[tipo] = guild.get_role(ruolo_id) if ruolo_id else None

        view = SetupWizardView(guild.id, passi, moduli, stato, ruoli, ETICHETTE_CATEGORIE)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))
