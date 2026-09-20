"""
cogs/utility/reminders.py
============================
Reminder personali (SPEC.md §14.16). Riusa lo scheduler generico già
esistente (core/scheduler.py, che aveva già "in futuro anche
promemoria" nel proprio docstring) — nessuna tabella nuova, nessun
timer in-processo che sparirebbe a un riavvio del bot.

Consegna: DM all'utente. Se i DM sono chiusi, fallback nel canale
dove il promemoria è stato impostato (menzionando l'utente) — solo
se quel canale esiste ancora ed è raggiungibile, altrimenti il
promemoria resta semplicemente non consegnato (loggato, non perso
silenziosamente: resta comunque marcato come eseguito, non viene
ritentato all'infinito per un canale sparito).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.duration_logic import format_duration, parse_duration
from core.premium import PremiumModule, registry
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.reminders")

MODULE_REMINDERS = "reminders"
REMINDER_ACTION_TYPE = "reminder_fire"


class RemindersCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def handle_reminder_fire(
        self, guild_id: int, user_id: int, payload: dict
    ) -> None:
        """Handler chiamato dallo scheduler quando un reminder scade."""
        testo_promemoria = payload.get("message", "(nessun testo)")
        testo = f"⏰ **Promemoria:** {testo_promemoria}"

        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                user = None

        if user is not None:
            try:
                await user.send(testo)
                return
            except discord.HTTPException:
                pass  # DM chiusi: proviamo il canale di fallback sotto

        channel_id = payload.get("channel_id")
        if channel_id is not None:
            guild = self.bot.get_guild(guild_id)
            channel = guild.get_channel(channel_id) if guild else None
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(f"<@{user_id}> {testo}")
                    return
                except discord.HTTPException:
                    pass

        logger.warning(
            "Impossibile consegnare il reminder dell'utente %s (server %s): "
            "DM chiusi e canale di fallback non disponibile.",
            user_id,
            guild_id,
        )

    # ================================================================
    # Comandi
    # ================================================================
    reminder_group = app_commands.Group(
        name="reminder", description="Promemoria personali."
    )

    @reminder_group.command(name="set", description="Imposta un promemoria.")
    @app_commands.describe(
        duration="Tra quanto tempo, es. 30m, 2h, 7d",
        message="Il testo del promemoria",
    )
    async def set_reminder(
        self, interaction: discord.Interaction, duration: str, message: str
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_REMINDERS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return

        try:
            duration_seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        execute_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        action_id = await scheduler.schedule(
            guild_id=guild.id,
            user_id=interaction.user.id,
            action_type=REMINDER_ACTION_TYPE,
            execute_at=execute_at,
            payload={"message": message, "channel_id": interaction.channel.id},
        )

        await interaction.response.send_message(
            f"⏰ Promemoria impostato tra **{format_duration(duration_seconds)}** "
            f"(ID `{action_id}`, usa `/reminder cancel` per annullarlo).",
            ephemeral=True,
        )

    @reminder_group.command(name="list", description="Mostra i tuoi promemoria in sospeso.")
    async def list_reminders(self, interaction: discord.Interaction) -> None:
        azioni = await scheduler.list_pending_for_user(
            interaction.user.id, REMINDER_ACTION_TYPE
        )
        if not azioni:
            await interaction.response.send_message(
                "Non hai promemoria in sospeso.", ephemeral=True
            )
            return

        righe = []
        for azione in azioni:
            quando = discord.utils.format_dt(azione["execute_at"], style="R")
            testo = azione["payload"].get("message", "(nessun testo)")
            righe.append(f"`#{azione['id']}` {quando} — {testo}")

        embed = discord.Embed(
            title="⏰ I tuoi promemoria",
            description="\n".join(righe),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reminder_group.command(name="cancel", description="Annulla un promemoria.")
    @app_commands.describe(reminder_id="ID del promemoria (mostrato da /reminder list)")
    async def cancel_reminder(
        self, interaction: discord.Interaction, reminder_id: int
    ) -> None:
        azione = await scheduler.get_pending_action(reminder_id)
        if (
            azione is None
            or azione["action_type"] != REMINDER_ACTION_TYPE
            or azione["executed"]
        ):
            await interaction.response.send_message(
                "Nessun promemoria trovato con questo ID.", ephemeral=True
            )
            return

        if azione["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "Puoi annullare solo i tuoi promemoria.", ephemeral=True
            )
            return

        await scheduler.cancel(reminder_id)
        await interaction.response.send_message("Promemoria annullato.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_REMINDERS,
            display_name="Reminders",
            description="Promemoria personali con consegna via DM (fallback nel canale).",
            premium_capable=False,
        )
    )
    cog = RemindersCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(REMINDER_ACTION_TYPE, cog.handle_reminder_fire)
