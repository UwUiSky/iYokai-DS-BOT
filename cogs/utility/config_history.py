"""
cogs/utility/config_history.py
==================================
Config Diff & Rollback (SPEC.md §2.7, BACKLOG.md §11). Legge/scrive
tramite i metodi già aggiunti a core/database.py (get_config_history,
rollback_config_change) — questo file è solo l'interfaccia comandi.

Nessun gate is_module_active_for_guild: è uno strumento diagnostico
per l'admin, non una feature del server da attivare/disattivare —
stesso principio di /setup, che deve funzionare anche PRIMA che
qualunque modulo sia attivo.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db


def _format_value(value) -> str:
    if value is None:
        return "*(mai impostato)*"
    return f"`{value}`"


class RollbackConfirmView(discord.ui.View):
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigHistoryCog(bot))
