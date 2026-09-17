"""
cogs/utility/owner_premium.py
================================
Comando riservato al proprietario del bot per accendere/spegnere
la natura Premium di ogni modulo, e per gestire la whitelist.

Questo è l'unico punto del progetto che può TRASFORMARE un modulo
gratuito in premium — e lo fa per tutti i server contemporaneamente
(eccetto quelli whitelistati). Per questo il controllo di identità
è il primo controllo di OGNI funzione qui dentro, prima di qualsiasi
altra logica.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.database import db
from core.premium import registry


def _is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == config.OWNER_ID


class OwnerPremiumCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    owner_group = app_commands.Group(
        name="owner",
        description="Comandi riservati al proprietario del bot.",
    )

    @owner_group.command(
        name="premium-list",
        description="[OWNER] Mostra lo stato premium di tutti i moduli.",
    )
    async def premium_list(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        modules = registry.all_modules()
        lines = []
        for m in modules:
            if not m.premium_capable:
                stato = "sempre gratuito"
            elif m.is_premium_active:
                stato = "PREMIUM ATTIVO"
            else:
                stato = "gratuito (predisposto)"
            lines.append(f"`{m.name}` — {m.display_name}: **{stato}**")

        testo = "\n".join(lines) if lines else "Nessun modulo registrato."
        await interaction.response.send_message(testo, ephemeral=True)

    @owner_group.command(
        name="premium-toggle",
        description="[OWNER] Accende o spegne la natura premium di un modulo.",
    )
    @app_commands.describe(
        module_name="Nome tecnico del modulo (vedi /owner premium-list)",
        active="True per rendere premium, False per rendere gratis",
    )
    async def premium_toggle(
        self,
        interaction: discord.Interaction,
        module_name: str,
        active: bool,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        module = registry.get(module_name)
        if module is None:
            await interaction.response.send_message(
                f"Modulo `{module_name}` non trovato. "
                f"Usa /owner premium-list per la lista esatta.",
                ephemeral=True,
            )
            return

        if not module.premium_capable:
            await interaction.response.send_message(
                f"`{module_name}` è marcato come sempre-gratuito "
                f"e non può diventare premium.",
                ephemeral=True,
            )
            return

        registry.set_module_premium(module_name, active)

        # Persistenza su database, così lo stato sopravvive a un
        # riavvio del bot (il registry in memoria viene ricostruito
        # dai cog, ma la flag premium va riletta da qui all'avvio —
        # TODO: caricare questo stato in main.py dopo load_all_cogs).
        await db.pool.execute(
            """
            INSERT INTO premium_module_flags (module_name, is_active, updated_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (module_name) DO UPDATE
                SET is_active = EXCLUDED.is_active,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
            """,
            module_name,
            active,
            interaction.user.id,
        )

        stato = "PREMIUM" if active else "GRATUITO"
        await interaction.response.send_message(
            f"Modulo `{module_name}` impostato su **{stato}**.",
            ephemeral=True,
        )

    @owner_group.command(
        name="whitelist-add",
        description="[OWNER] Aggiunge un server alla whitelist premium.",
    )
    @app_commands.describe(
        guild_id="ID del server da aggiungere",
        reason="Motivo (facoltativo)",
    )
    async def whitelist_add(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        reason: str | None = None,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message(
                "ID server non valido.", ephemeral=True
            )
            return

        await db.add_guild_to_whitelist(gid, interaction.user.id, reason)
        await interaction.response.send_message(
            f"Server `{gid}` aggiunto alla whitelist premium.",
            ephemeral=True,
        )

    @owner_group.command(
        name="whitelist-remove",
        description="[OWNER] Rimuove un server dalla whitelist premium.",
    )
    @app_commands.describe(guild_id="ID del server da rimuovere")
    async def whitelist_remove(
        self, interaction: discord.Interaction, guild_id: str
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message(
                "ID server non valido.", ephemeral=True
            )
            return

        await db.remove_guild_from_whitelist(gid)
        await interaction.response.send_message(
            f"Server `{gid}` rimosso dalla whitelist premium.",
            ephemeral=True,
        )

    @owner_group.command(
        name="memory-status",
        description="[OWNER] Mostra il consumo di RAM attuale del processo.",
    )
    async def memory_status(self, interaction: discord.Interaction) -> None:
        # Vive in questo file (nominalmente "premium") e non in un
        # proprio file dedicato per un motivo tecnico, non di
        # comodità: app_commands.Group con lo stesso nome "owner"
        # registrato da due cog diversi verrebbe rifiutato da
        # discord.py come comando duplicato. Finché il progetto ha un
        # solo gruppo /owner, i comandi owner-only condividono questo
        # file — da riorganizzare se/quando il gruppo crescerà troppo.
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        from core.memory_guard import memory_guard
        from core.memory_guard_logic import format_memory_status

        rss = memory_guard.read_rss_bytes()
        await interaction.response.send_message(
            format_memory_status(rss, config.MEMORY_ALERT_THRESHOLD_MB),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OwnerPremiumCog(bot))
