"""
cogs/utility/scheduled_messages.py
======================================
Scheduled Messages (SPEC.md §14.17). Riusa lo stesso scheduler
generico già usato per i Reminder (core/scheduler.py) — nessuna
tabella nuova. Diversamente dai Reminder (personali, consegnati via
DM), questi sono uno strumento admin: un messaggio programmato per
un CANALE del server, non per un singolo utente.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.admin_mentions_logic import menzioni_ammesse, utente_puo_pingare_ruoli
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.duration_logic import format_duration, parse_duration
from core.premium import PremiumModule, registry
from core.lista_limiti_logic import righe_entro_limite
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.scheduled_messages")

MODULE_SCHEDULED_MESSAGES = "scheduled_messages"
SCHEDULED_MESSAGE_ACTION_TYPE = "scheduled_message_fire"

# LIM-12: un messaggio normale sta in 2000 caratteri; 1800 lascia margine ai
# segnaposto e alle menzioni che Discord espande.
TestoProgrammato = app_commands.Range[str, 1, 1800]


class ScheduledMessagesCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _avvisa_autore(self, user_id: int, testo: str) -> None:
        """M 10.5: se il messaggio non parte, chi l'ha programmato lo deve sapere."""
        try:
            utente = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            await utente.send(testo)
        except (discord.HTTPException, AttributeError):
            logger.warning("Non sono riuscito ad avvisare l'utente %s dell'invio fallito.", user_id)

    async def handle_scheduled_message_fire(
        self, guild_id: int, user_id: int, payload: dict
    ) -> None:
        """Handler chiamato dallo scheduler quando un messaggio programmato scade."""
        channel_id = payload.get("channel_id")
        testo = payload.get("message", "")
        anteprima = testo[:100] + ("…" if len(testo) > 100 else "")

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None

        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                "Impossibile pubblicare il messaggio programmato nel server %s: "
                "canale %s non raggiungibile.",
                guild_id,
                channel_id,
            )
            await self._avvisa_autore(
                user_id,
                f"Il messaggio che avevi programmato non è stato pubblicato: il canale "
                f"<#{channel_id}> non esiste più o non lo vedo.\n> {anteprima}",
            )
            return

        try:
            await channel.send(
                testo,
                allowed_mentions=menzioni_ammesse(bool(payload.get("ping_ruoli", False))),
            )
        except discord.HTTPException as errore:
            logger.warning(
                "Impossibile pubblicare il messaggio programmato nel canale %s "
                "(server %s): %s",
                channel_id,
                guild_id,
                errore,
            )
            await self._avvisa_autore(
                user_id,
                f"Il messaggio che avevi programmato non è stato pubblicato in "
                f"{channel.mention}: permessi insufficienti o errore di Discord.\n> {anteprima}",
            )

    # ================================================================
    # Comandi
    # ================================================================
    @comando_di_gruppo(
        "admin",
        nome="programma",
        descrizione="Programma un messaggio.",
        sottogruppo=("messaggi", "Messaggi programmati e messaggi fissi"),
    )
    @app_commands.describe(
        channel="Il canale dove pubblicare il messaggio",
        duration="Tra quanto tempo, es. 2h, 1d, 7d",
        message="Il testo del messaggio",
    )
    async def set_scheduled_message(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        duration: str,
        message: TestoProgrammato,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_SCHEDULED_MESSAGES):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
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
            action_type=SCHEDULED_MESSAGE_ACTION_TYPE,
            execute_at=execute_at,
            payload={
                "channel_id": channel.id,
                "message": message,
                # D12: i ruoli del testo vengono avvisati solo se chi programma può menzionarli.
                "ping_ruoli": utente_puo_pingare_ruoli(interaction.user),
            },
        )

        await interaction.response.send_message(
            f"📅 Messaggio programmato per {channel.mention} tra "
            f"**{format_duration(duration_seconds)}** "
            f"(ID `{action_id}`, usa `/admin messaggi annulla` per annullarlo).",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin",
        nome="programmati",
        descrizione="Mostra i messaggi programmati di questo server.",
        sottogruppo=("messaggi", "Messaggi programmati e messaggi fissi"),
    )
    async def list_scheduled_messages(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        azioni = await scheduler.list_pending_for_guild(guild.id, SCHEDULED_MESSAGE_ACTION_TYPE)
        if not azioni:
            await interaction.response.send_message(
                "Nessun messaggio programmato per questo server.", ephemeral=True
            )
            return

        righe = []
        for azione in azioni:
            quando = discord.utils.format_dt(azione["execute_at"], style="R")
            channel_id = azione["payload"].get("channel_id")
            testo = azione["payload"].get("message", "(nessun testo)")
            righe.append(f"`#{azione['id']}` {quando} in <#{channel_id}> — {testo[:80]}")

        descrizione, _ = righe_entro_limite(righe, 4000)  # LIM-13: 4096 al massimo
        embed = discord.Embed(
            title="📅 Messaggi programmati",
            description=descrizione,
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "admin",
        nome="annulla",
        descrizione="Annulla un messaggio programmato.",
        sottogruppo=("messaggi", "Messaggi programmati e messaggi fissi"),
    )
    @app_commands.describe(schedule_id="ID (mostrato da /admin messaggi programmati)")
    async def cancel_scheduled_message(
        self, interaction: discord.Interaction, schedule_id: int
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return

        azione = await scheduler.get_pending_action(schedule_id)
        if (
            azione is None
            or azione["action_type"] != SCHEDULED_MESSAGE_ACTION_TYPE
            or azione["executed"]
            or azione["guild_id"] != guild.id
        ):
            await interaction.response.send_message(
                "Nessun messaggio programmato trovato con questo ID in questo server.",
                ephemeral=True,
            )
            return

        await scheduler.cancel(schedule_id)
        await interaction.response.send_message("Messaggio programmato annullato.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_SCHEDULED_MESSAGES,
            display_name="Scheduled Messages",
            category="utility",
            description="Messaggi programmati per un canale, in futuro.",
            premium_capable=False,
        )
    )
    cog = ScheduledMessagesCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(SCHEDULED_MESSAGE_ACTION_TYPE, cog.handle_scheduled_message_fire)
