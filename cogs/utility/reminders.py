"""
cogs/utility/reminders.py
============================
Reminder personali (SPEC.md §14.16). Riusa lo scheduler generico
(core/scheduler.py): nessuna tabella nuova, nessun timer in memoria
che sparirebbe a un riavvio del bot.

Consegna: DM all'utente, oppure nel canale se lo chiede. Se i DM sono
chiusi, ripiego nel canale dove il promemoria è stato impostato
(menzionando l'utente), se esiste ancora; altrimenti resta non
consegnato (scritto nel log, non ritentato all'infinito).
Catalogo #128: promemoria che si ripete (UTL-098), nel canale invece
che in DM (UTL-099), annullare tutti i propri (UTL-102), lo staff vede
e annulla quelli del server (UTL-103).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.command_access import Livello, puo_usare
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.duration_logic import format_duration, parse_duration
from core.lista_limiti_logic import righe_entro_limite
from core.premium import PremiumModule, registry
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.reminders")

MODULE_REMINDERS = "reminders"
REMINDER_ACTION_TYPE = "reminder_fire"

# LIM-13: il testo finale ("⏰ Promemoria: " + testo, più la menzione nel canale
# di ripiego) deve stare in 2000 caratteri.
TestoPromemoria = app_commands.Range[str, 1, 1800]
# Un promemoria che si ripete non scatta più spesso di così.
MIN_RIPETIZIONE_SECONDI = 30 * 60
# Promemoria in sospeso per persona: senza tetto i ripetuti nel canale diventano spam.
MAX_PROMEMORIA_PER_UTENTE = 25
SOTTOGRUPPO = ("reminder", "Promemoria personali")


class RemindersCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def handle_reminder_fire(
        self, guild_id: int, user_id: int, payload: dict
    ) -> None:
        """Handler chiamato dallo scheduler quando un reminder scade."""
        testo_promemoria = payload.get("message", "(nessun testo)")
        testo = f"⏰ **Promemoria:** {testo_promemoria}"
        ripeti = payload.get("ripeti")
        if ripeti or payload.get("nel_canale"):
            # Chi è uscito dal server non riceve più ripetuti né messaggi nel canale.
            server = self.bot.get_guild(guild_id)
            if server is None or server.get_member(user_id) is None:
                logger.info("Promemoria di %s fermato: non è più nel server %s.", user_id, guild_id)
                return
        if ripeti:
            # Si riprogramma prima di consegnare: un errore di consegna non ferma la serie.
            await scheduler.schedule(
                guild_id, user_id, REMINDER_ACTION_TYPE,
                datetime.now(timezone.utc) + timedelta(seconds=int(ripeti)), payload,
            )

        if not payload.get("nel_canale"):
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
                    # Il testo l'ha scritto l'utente: può pingare solo se stesso,
                    # mai @everyone né ruoli.
                    await channel.send(
                        f"<@{user_id}> {testo}",
                        allowed_mentions=discord.AllowedMentions(
                            everyone=False, roles=False, users=[discord.Object(id=user_id)]
                        ),
                    )
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
    @comando_di_gruppo(
        "utility",
        nome="set",
        descrizione="Imposta un promemoria.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        duration="Tra quanto tempo, es. 30m, 2h, 7d",
        message="Il testo del promemoria",
        ripeti="Ripeti ogni..., es. 1d o 1w (minimo 30m)",
        nel_canale="Scrivilo in questo canale invece che in privato",
    )
    async def set_reminder(
        self,
        interaction: discord.Interaction,
        duration: app_commands.Range[str, 2, 10],
        message: TestoPromemoria,
        ripeti: app_commands.Range[str, 2, 10] | None = None,
        nel_canale: bool = False,
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
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return

        try:
            duration_seconds = parse_duration(duration)
            ripeti_secondi = parse_duration(ripeti) if ripeti else None
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        if ripeti_secondi is not None and ripeti_secondi < MIN_RIPETIZIONE_SECONDI:
            await interaction.response.send_message(
                "Un promemoria si può ripetere al massimo ogni 30 minuti.", ephemeral=True
            )
            return
        if nel_canale and not interaction.channel.permissions_for(interaction.user).send_messages:
            await interaction.response.send_message(
                "Non puoi scrivere in questo canale: il promemoria nel canale non si può impostare qui.",
                ephemeral=True,
            )
            return
        in_sospeso = await scheduler.list_pending_for_user(
            interaction.user.id, REMINDER_ACTION_TYPE, MAX_PROMEMORIA_PER_UTENTE
        )
        if len(in_sospeso) >= MAX_PROMEMORIA_PER_UTENTE:
            await interaction.response.send_message(
                f"Puoi avere al massimo {MAX_PROMEMORIA_PER_UTENTE} promemoria in sospeso: "
                "annullane qualcuno con /utility reminder cancel.",
                ephemeral=True,
            )
            return

        payload = {"message": message, "channel_id": interaction.channel.id}
        if ripeti_secondi is not None:
            payload["ripeti"] = ripeti_secondi
        if nel_canale:
            payload["nel_canale"] = True
        execute_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        action_id = await scheduler.schedule(
            guild_id=guild.id,
            user_id=interaction.user.id,
            action_type=REMINDER_ACTION_TYPE,
            execute_at=execute_at,
            payload=payload,
        )

        testo = f"⏰ Promemoria impostato tra **{format_duration(duration_seconds)}**"
        if ripeti_secondi is not None:
            testo += f", poi ogni **{format_duration(ripeti_secondi)}**"
        testo += f" (ID `{action_id}`, usa `/utility reminder cancel` per annullarlo)."
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "utility",
        nome="list",
        descrizione="Mostra i tuoi promemoria in sospeso.",
        sottogruppo=SOTTOGRUPPO,
    )
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

        descrizione, _ = righe_entro_limite(righe, 4000)  # LIM-13: 4096 al massimo
        embed = discord.Embed(
            title="⏰ I tuoi promemoria",
            description=descrizione,
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "utility",
        nome="cancel",
        descrizione="Annulla un promemoria, o tutti i tuoi.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        reminder_id="ID del promemoria (mostrato da /utility reminder list)",
        tutti="Annulla tutti i tuoi promemoria",
    )
    async def cancel_reminder(
        self, interaction: discord.Interaction, reminder_id: int | None = None, tutti: bool = False
    ) -> None:
        if tutti:
            azioni = await scheduler.list_pending_for_user(interaction.user.id, REMINDER_ACTION_TYPE, 100)
            for azione in azioni:
                await scheduler.cancel(azione["id"])
            await interaction.response.send_message(f"Annullati {len(azioni)} promemoria.", ephemeral=True)
            return
        if reminder_id is None:
            await interaction.response.send_message(
                "Indica l'ID del promemoria oppure scegli «tutti».", ephemeral=True
            )
            return

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

        if azione["user_id"] != interaction.user.id and not await self._staff_del_server(interaction, azione):
            await interaction.response.send_message(
                "Puoi annullare solo i tuoi promemoria.", ephemeral=True
            )
            return

        await scheduler.cancel(reminder_id)
        await interaction.response.send_message("Promemoria annullato.", ephemeral=True)

    @staticmethod
    async def _staff_del_server(interaction: discord.Interaction, azione: dict) -> bool:
        """UTL-103: un admin del server può annullare i promemoria impostati nel suo server."""
        guild = interaction.guild
        return guild is not None and azione["guild_id"] == guild.id and await puo_usare(interaction, Livello.ADMIN)

    @comando_di_gruppo(
        "utility",
        nome="server",
        descrizione="Per lo staff: i promemoria impostati in questo server.",
        sottogruppo=SOTTOGRUPPO,
    )
    async def server_reminders(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or not await puo_usare(interaction, Livello.ADMIN):
            await interaction.response.send_message("Solo gli admin del server vedono questo elenco.", ephemeral=True)
            return
        azioni = await scheduler.list_pending_for_guild(guild.id, REMINDER_ACTION_TYPE, 100)
        if not azioni:
            await interaction.response.send_message("Nessun promemoria in sospeso in questo server.", ephemeral=True)
            return
        righe = [
            f"`#{a['id']}` <@{a['user_id']}> {discord.utils.format_dt(a['execute_at'], style='R')} — "
            f"{str(a['payload'].get('message', ''))[:80]}"
            for a in azioni
        ]
        descrizione, _ = righe_entro_limite(righe, 4000)
        embed = discord.Embed(title="⏰ Promemoria del server", description=descrizione, color=discord.Color.blurple())
        embed.set_footer(text="Per annullarne uno: /utility reminder cancel con l'ID.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_REMINDERS,
            display_name="Reminders",
            category="utility",
            description="Promemoria personali con consegna via DM (fallback nel canale).",
            premium_capable=False,
        )
    )
    cog = RemindersCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(REMINDER_ACTION_TYPE, cog.handle_reminder_fire)
