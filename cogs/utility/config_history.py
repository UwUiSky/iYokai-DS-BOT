"""
cogs/utility/config_history.py
==================================
Config Diff & Rollback (SPEC.md §2.7, BACKLOG.md §11), più Reset
(§2.1), Esporta/Importa (§2.5/§2.6) e Lingua per server (§2.3).
Legge/scrive tramite i metodi già aggiunti a core/database.py
(get_config_history, rollback_config_change, get_full_config,
import_full_config, reset_guild_config, get/set_guild_language) —
questo file è solo l'interfaccia comandi.

Nessun gate is_module_active_for_guild: è uno strumento diagnostico/
di gestione per l'admin, non una feature del server da attivare/
disattivare — stesso principio di /setup, che deve funzionare anche
PRIMA che qualunque modulo sia attivo.

Nota su §2.3 (Lingua per server): qui si costruisce l'INFRASTRUTTURA
(colonna già esistente, comando per leggerla/scriverla,
`core/i18n.py` con un piccolo registro di traduzioni) — non un
sistema i18n applicato a TUTTO il testo del bot, che resterebbe
comunque in italiano nella stragrande maggioranza dei cog. Marcato
`[~]` in SPEC.md apposta, non `[x]`: sarebbe disonesto dichiararlo
completo.
"""

from __future__ import annotations

import io
import json

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.ui_base import BaseView

SUPPORTED_LANGUAGES = ("it", "en")


def _format_value(value) -> str:
    if value is None:
        return "*(mai impostato)*"
    return f"`{value}`"


class RollbackConfirmView(BaseView):
    """
    Conferma a due passaggi (non persistente — è un'interazione breve
    legata a un singolo comando, non un pannello a vita lunga come i
    ticket o il verify: stesso ragionamento già fatto per
    AppealActionsView in cogs/security/spam_trap.py).
    """

    def __init__(self, entry_id: int, requested_by_id: int) -> None:
        super().__init__(timeout=60)
        self.entry_id = entry_id
        self.requested_by_id = requested_by_id

    @discord.ui.button(label="Conferma rollback", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                "Solo chi ha richiesto il rollback può confermarlo.", ephemeral=True
            )
            return

        riuscito = await db.rollback_config_change(
            self.entry_id, rolled_back_by=interaction.user.id
        )
        for child in self.children:
            child.disabled = True
        self.stop()

        if riuscito:
            await interaction.response.edit_message(
                content="✅ Rollback eseguito.", view=self
            )
        else:
            await interaction.response.edit_message(
                content="❌ Questa voce di storico non esiste più.", view=self
            )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                "Solo chi ha richiesto il rollback può annullarlo.", ephemeral=True
            )
            return
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(content="Rollback annullato.", view=self)


class ResetConfirmView(BaseView):
    """
    SPEC.md §2.1: conferma a due passaggi, stesso schema di
    RollbackConfirmView — un reset disattiva TUTTI i moduli e
    svuota tutte le settings, non un'azione da eseguire per errore
    con un solo click.
    """

    def __init__(self, guild_id: int, requested_by_id: int) -> None:
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.requested_by_id = requested_by_id

    @discord.ui.button(label="Conferma reset", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                "Solo chi ha richiesto il reset può confermarlo.", ephemeral=True
            )
            return

        await db.reset_guild_config(self.guild_id, changed_by=interaction.user.id)
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(
            content="✅ Configurazione azzerata: nessun modulo attivo, nessuna "
            "impostazione, lingua tornata a italiano. Usa /config rollback per "
            "annullare se necessario.",
            view=self,
        )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                "Solo chi ha richiesto il reset può annullarlo.", ephemeral=True
            )
            return
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(content="Reset annullato.", view=self)


class ConfigHistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    config_group = app_commands.Group(
        name="config", description="Storico delle modifiche di configurazione del server."
    )

    @config_group.command(
        name="history", description="[Admin] Mostra le ultime modifiche alla configurazione."
    )
    @app_commands.describe(limit="Quante voci mostrare (default 10, massimo 25)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def history(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 25] = 10,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        voci = await db.get_config_history(guild.id, limit=limit)
        if not voci:
            await interaction.response.send_message(
                "Nessuna modifica registrata finora.", ephemeral=True
            )
            return

        righe = []
        for voce in voci:
            autore = f"<@{voce.changed_by}>" if voce.changed_by else "sconosciuto"
            righe.append(
                f"`#{voce.id}` **{voce.change_type}** `{voce.key_name}`: "
                f"{_format_value(voce.old_value)} → {_format_value(voce.new_value)} "
                f"— {autore}"
            )

        embed = discord.Embed(
            title="📜 Storico configurazione",
            description="\n".join(righe),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Usa /config rollback <id> per annullare una voce specifica.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(
        name="rollback", description="[Admin] Ripristina il valore precedente di una modifica."
    )
    @app_commands.describe(entry_id="ID della voce di storico (mostrato da /config history)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def rollback(self, interaction: discord.Interaction, entry_id: int) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        entry = await db.get_config_history_entry(entry_id)
        if entry is None or entry.guild_id != guild.id:
            await interaction.response.send_message(
                "Nessuna voce di storico trovata con questo ID in questo server.",
                ephemeral=True,
            )
            return

        view = RollbackConfirmView(entry_id, interaction.user.id)
        await interaction.response.send_message(
            f"Confermi di voler ripristinare `{entry.key_name}` a "
            f"{_format_value(entry.old_value)} (era {_format_value(entry.new_value)})?",
            view=view,
            ephemeral=True,
        )

    @config_group.command(
        name="reset", description="[Admin] Azzera la configurazione di questo server."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reset(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        view = ResetConfirmView(guild.id, interaction.user.id)
        await interaction.response.send_message(
            "⚠️ Confermi di voler disattivare **tutti** i moduli e azzerare "
            "**tutte** le impostazioni di questo server? L'operazione è "
            "annullabile con /config rollback.",
            view=view,
            ephemeral=True,
        )

    @config_group.command(
        name="export", description="[Admin] Esporta la configurazione di questo server in un file."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def export(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config = await db.get_full_config(guild.id)
        contenuto = json.dumps(config, indent=2, ensure_ascii=False)
        file = discord.File(
            io.BytesIO(contenuto.encode("utf-8")),
            filename=f"iyokai-config-{guild.id}.json",
        )
        await interaction.response.send_message(
            "Configurazione esportata. Usa /config import su un altro server "
            "per applicarla (SOVRASCRIVE tutto ciò che c'è già).",
            file=file,
            ephemeral=True,
        )

    @config_group.command(
        name="import", description="[Admin] Importa una configurazione da un file esportato con /config export."
    )
    @app_commands.describe(file="Il file .json prodotto da /config export")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def import_config(
        self, interaction: discord.Interaction, file: discord.Attachment
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        try:
            grezzo = await file.read()
            dati = json.loads(grezzo.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            await interaction.response.send_message(
                "Il file non è un JSON valido (probabilmente non prodotto da /config export).",
                ephemeral=True,
            )
            return

        if not isinstance(dati, dict) or not {"modules", "settings", "language"} <= dati.keys():
            await interaction.response.send_message(
                "Il file non ha il formato atteso (mancano modules/settings/language).",
                ephemeral=True,
            )
            return

        await db.import_full_config(
            guild.id,
            modules=dati["modules"],
            settings=dati["settings"],
            language=dati["language"],
            changed_by=interaction.user.id,
        )
        await interaction.response.send_message(
            f"✅ Configurazione importata: {len(dati['modules'])} moduli, "
            f"{len(dati['settings'])} impostazioni, lingua `{dati['language']}`. "
            f"Annullabile con /config rollback.",
            ephemeral=True,
        )

    # ================================================================
    # SPEC.md §2.3 — Lingua per server
    # ================================================================
    language_group = app_commands.Group(
        name="language", description="Lingua del server (infrastruttura, vedi SPEC.md §2.3).", parent=config_group
    )

    @language_group.command(name="show", description="Mostra la lingua impostata per questo server.")
    async def language_show(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        lingua = await db.get_guild_language(interaction.guild.id)
        await interaction.response.send_message(f"Lingua attuale: `{lingua}`.", ephemeral=True)

    @language_group.command(name="set", description="[Admin] Imposta la lingua di questo server.")
    @app_commands.describe(language="Codice lingua")
    @app_commands.choices(
        language=[app_commands.Choice(name=l, value=l) for l in SUPPORTED_LANGUAGES]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def language_set(
        self, interaction: discord.Interaction, language: app_commands.Choice[str]
    ) -> None:
        if interaction.guild is None:
            return
        await db.set_guild_language(interaction.guild.id, language.value, changed_by=interaction.user.id)
        await interaction.response.send_message(
            f"Lingua impostata su `{language.value}`. Nota: solo una parte "
            f"limitata dei messaggi del bot usa questa impostazione per ora.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigHistoryCog(bot))
