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
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.database import db
from core.duration_logic import format_duration, parse_duration
from core.i18n import testo_per
from core.premium import PremiumModule, registry
from core.lista_limiti_logic import righe_entro_limite
from core import programmati_logic as prog
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.scheduled_messages")

MODULE_SCHEDULED_MESSAGES = "scheduled_messages"
SCHEDULED_MESSAGE_ACTION_TYPE = "scheduled_message_fire"

# LIM-12: un messaggio normale sta in 2000 caratteri; 1800 lascia margine ai
# segnaposto e alle menzioni che Discord espande.
TestoProgrammato = app_commands.Range[str, 1, 1800]


async def _completa_ripetuti(interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[int]]:
    if interaction.guild is None:
        return []
    azioni = await scheduler.list_pending_for_guild(interaction.guild.id, SCHEDULED_MESSAGE_ACTION_TYPE, limit=200)
    scelte = []
    for a in azioni:
        testo = str(a["payload"].get("message", ""))
        if prog.giro_di(a["payload"]) and corrente.strip().casefold() in f"{a['id']} {testo}".casefold():
            scelte.append(app_commands.Choice(name=f"#{a['id']} {testo[:80]}"[:100], value=int(a["id"])))
    return scelte[:25]


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
        ripeti = prog.giro_di(payload)
        prossimo_id = None
        if ripeti:
            # Prima il prossimo giro, poi l'invio: se il bot si ferma in mezzo, la serie non si perde. L'handler
            # non rilancia mai gli errori, quindi lo scheduler non lo ripete e non nascono doppioni.
            prossimo_id, _ = await self._riprogramma(guild_id, user_id, payload, ripeti)

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

        if payload.get("salta_se_ultimo"):
            try:
                ultimo = [m async for m in channel.history(limit=1)]
            except discord.HTTPException:
                ultimo = []
            if prog.deve_saltare(True, ultimo[0].id if ultimo else None, payload.get("ultimo_id")):
                return

        try:
            inviato = await channel.send(
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
            return
        if prossimo_id and payload.get("salta_se_ultimo"):
            await self._ricorda_ultimo(prossimo_id, inviato.id)
        ruolo_id = payload.get("ping_ruolo_id")
        if ruolo_id:
            try:
                # Un secondo messaggio per avvisare: la notifica arriva comunque, il canale resta pulito.
                await channel.send(
                    f"<@&{int(ruolo_id)}>",
                    delete_after=prog.SECONDI_PING_BREVE,
                    allowed_mentions=discord.AllowedMentions(roles=[discord.Object(int(ruolo_id))], everyone=False, users=False),
                )
            except discord.HTTPException as errore:
                logger.warning("Ping breve non inviato nel canale %s: %s", channel_id, errore)

    async def _riprogramma(self, guild_id: int, user_id: int, payload: dict, ripeti: int) -> tuple[int, datetime]:
        adesso = datetime.now(timezone.utc)
        try:
            precedente = datetime.fromisoformat(payload["quando"])
        except (KeyError, ValueError):
            precedente = adesso
        ora = prog.leggi_ora(payload["ora"]) if payload.get("ora") else None
        prossimo = prog.prossimo_giro(precedente, ripeti, adesso, ora, prog.fuso_valido(payload.get("fuso")))
        nuovo = {**payload, "quando": prossimo.isoformat()}
        nuovo_id = await scheduler.schedule(
            guild_id=guild_id, user_id=user_id, action_type=SCHEDULED_MESSAGE_ACTION_TYPE, execute_at=prossimo, payload=nuovo
        )
        return nuovo_id, prossimo

    async def _ricorda_ultimo(self, azione_id: int, messaggio_id: int) -> None:
        """Il giro già in coda ricorda l'ultimo messaggio nostro, per sapere se il canale è rimasto fermo."""
        from core.database import db

        await db.pool.execute(
            "UPDATE scheduled_actions SET payload = jsonb_set(payload, '{ultimo_id}', to_jsonb($2::bigint)) "
            "WHERE id = $1 AND executed = FALSE",
            azione_id, messaggio_id,
        )

    # ================================================================
    # Comandi
    # ================================================================
    @comando_di_gruppo(
        "admin-messaggi",
        nome="crea",
        descrizione="Programma un messaggio.",
        sottogruppo=SOTTOGRUPPI["admin-messaggi programmati"],
    )
    @app_commands.describe(
        channel="Il canale dove pubblicare il messaggio",
        duration="Tra quanto tempo, es. 2h, 1d, 7d",
        message="Il testo del messaggio",
        ripeti="Ripeti ogni, es. 30m, 6h, 2d (almeno 10 minuti)",
        ora="Ripeti ogni giorno a quest'ora fissa (HH:MM, fuso del server)",
        salta_se_ultimo="Non ripetere se l'ultimo messaggio del canale è già questo",
        ping_ruolo="Un ruolo da avvisare con un secondo messaggio (sparisce dopo 10 s)",
    )
    async def set_scheduled_message(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        duration: app_commands.Range[str, 1, 20],
        message: TestoProgrammato,
        ripeti: app_commands.Range[str, 2, 20] | None = None,
        ora: app_commands.Range[str, 4, 5] | None = None,
        salta_se_ultimo: bool = False,
        ping_ruolo: discord.Role | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_SCHEDULED_MESSAGES):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return

        try:
            duration_seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        execute_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        extra, errore = await self._opzioni_ripetizione(
            interaction, guild, execute_at, ripeti, ora, salta_se_ultimo, ping_ruolo
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        if extra.get("ora"):
            execute_at = datetime.fromisoformat(extra["quando"])
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
                **extra,
            },
        )

        await interaction.response.send_message(
            await testo_per(interaction, "scheduledmes_messaggio_programmato_per_tra_id", mention=channel.mention, v2=format_duration(duration_seconds), action_id=action_id),
            ephemeral=True,
        )

    async def _opzioni_ripetizione(
        self, interaction, guild, primo: datetime, ripeti, ora, salta_se_ultimo: bool, ping_ruolo
    ) -> tuple[dict, str | None]:
        """Le chiavi in più del payload (ripetizione, ora fissa, salto, ping breve) o un errore per l'utente."""
        extra: dict = {}
        if ora and not ripeti:
            ripeti = "1d"  # un'ora fissa senza altro vuol dire «ogni giorno»
        secondi = None
        if ripeti:
            try:
                secondi = parse_duration(ripeti)
                orario = prog.leggi_ora(ora) if ora else None
            except ValueError as exc:
                return {}, str(exc)
            errore = prog.errore_ripetizione(secondi, orario)
            if errore:
                return {}, errore
            presenti = await scheduler.list_pending_for_guild(guild.id, SCHEDULED_MESSAGE_ACTION_TYPE, limit=200)
            if sum(1 for a in presenti if prog.giro_di(a["payload"])) >= prog.MAX_SERIE_PER_SERVER:
                return {}, await testo_per(interaction, "programmati_troppe_serie", massimo=prog.MAX_SERIE_PER_SERVER)
            extra = {"ripeti": secondi, "quando": primo.isoformat()}
            if orario:
                fuso = prog.FUSO_PREDEFINITO
                extra.update({"ora": f"{orario:%H:%M}", "fuso": fuso,
                              "quando": prog.prima_ora_fissa(primo, orario, prog.fuso_valido(fuso)).isoformat()})
        elif ora:
            return {}, await testo_per(interaction, "programmati_ora_senza_ripeti")
        if salta_se_ultimo:
            if not secondi:
                return {}, await testo_per(interaction, "programmati_salta_senza_ripeti")
            extra["salta_se_ultimo"] = True
        if ping_ruolo is not None:
            if not utente_puo_pingare_ruoli(interaction.user):
                return {}, await testo_per(interaction, "programmati_ping_senza_permesso")
            if not (ping_ruolo.mentionable or guild.me.guild_permissions.mention_everyone):
                return {}, await testo_per(interaction, "programmati_ping_ruolo_non_menzionabile")
            extra["ping_ruolo_id"] = ping_ruolo.id
        return extra, None

    @comando_di_gruppo(
        "admin-messaggi",
        nome="salta",
        descrizione="Salta il prossimo giro di un messaggio che si ripete.",
        sottogruppo=SOTTOGRUPPI["admin-messaggi programmati"],
    )
    @app_commands.describe(id="Il messaggio programmato (scrivi per cercare)")
    @app_commands.autocomplete(id=_completa_ripetuti)
    async def salta_giro(self, interaction: discord.Interaction, id: int) -> None:
        guild = interaction.guild
        azione = await scheduler.get_pending_action(id)
        if (
            azione is None or azione["action_type"] != SCHEDULED_MESSAGE_ACTION_TYPE
            or azione["executed"] or azione["guild_id"] != guild.id
        ):
            await interaction.response.send_message(
                await testo_per(interaction, "scheduledmes_nessun_messaggio_programmato_trovato_con"), ephemeral=True
            )
            return
        payload = azione["payload"]
        ripeti = prog.giro_di(payload)
        if not ripeti:
            await interaction.response.send_message(await testo_per(interaction, "programmati_non_si_ripete"), ephemeral=True)
            return
        await scheduler.cancel(id)
        nuovo_id, prossimo = await self._riprogramma(guild.id, azione["user_id"], payload, ripeti)
        await interaction.response.send_message(
            await testo_per(interaction, "programmati_saltato", id=nuovo_id, quando=discord.utils.format_dt(prossimo, style="R")),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        try:
            await scheduler.cancel_for_channel(channel.guild.id, SCHEDULED_MESSAGE_ACTION_TYPE, channel.id)
        except Exception:
            logger.exception("Messaggi programmati: pulizia del canale %s fallita", channel.id)

    @comando_di_gruppo(
        "admin-messaggi",
        nome="elenco",
        descrizione="Mostra i messaggi programmati di questo server.",
        sottogruppo=SOTTOGRUPPI["admin-messaggi programmati"],
    )
    async def list_scheduled_messages(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        azioni = await scheduler.list_pending_for_guild(guild.id, SCHEDULED_MESSAGE_ACTION_TYPE)
        if not azioni:
            await interaction.response.send_message(
                await testo_per(interaction, "scheduledmes_nessun_messaggio_programmato_per_questo"), ephemeral=True
            )
            return

        righe = []
        for azione in azioni:
            quando = discord.utils.format_dt(azione["execute_at"], style="R")
            channel_id = azione["payload"].get("channel_id")
            testo = azione["payload"].get("message", "(nessun testo)")
            giro = prog.giro_di(azione["payload"])
            segno = f" 🔁 ogni {format_duration(giro)}" if giro else ""
            righe.append(f"`#{azione['id']}` {quando}{segno} in <#{channel_id}> — {testo[:80]}")

        descrizione, _ = righe_entro_limite(righe, 4000)  # LIM-13: 4096 al massimo
        embed = discord.Embed(
            title=await testo_per(interaction, "scheduledmes_messaggi_programmati"),
            description=descrizione,
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "admin-messaggi",
        nome="annulla",
        descrizione="Annulla un messaggio programmato.",
        sottogruppo=SOTTOGRUPPI["admin-messaggi programmati"],
    )
    @app_commands.describe(schedule_id="ID (mostrato da /admin-messaggi programmati elenco)")
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
                await testo_per(interaction, "scheduledmes_nessun_messaggio_programmato_trovato_con"),
                ephemeral=True,
            )
            return

        await scheduler.cancel(schedule_id)
        await interaction.response.send_message(await testo_per(interaction, "scheduledmes_messaggio_programmato_annullato"), ephemeral=True)


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
