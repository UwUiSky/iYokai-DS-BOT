"""
cogs/moderation/actions.py
=============================
Azioni di moderazione base: warn, kick, ban, unban, tempban, timeout,
untimeout. Modulo SEMPRE GRATUITO (MODULE_ACTIONS, premium_capable=
False), coerente con lo schema di progetto ("Azioni base" è [Free]).

Ogni comando segue lo stesso schema in quattro passi:
  1. ensure_module_enabled — il server ha attivato la moderazione?
  2. check_can_moderate — chi comanda può agire su questo bersaglio?
     (gerarchia ruoli, owner, bot stesso — vedi core/permissions.py)
  3. azione vera su Discord (kick/ban/timeout...)
  4. registrazione del caso nel case system + risposta + log

Il tempban è l'unico caso "speciale": non esiste un ban a tempo
nativo su Discord, quindi banniamo normalmente e PIANIFICHIAMO lo
sblocco tramite core/scheduler.py, che sopravvive a un riavvio del
bot (vedi quel file per il perché serve, non un semplice
asyncio.sleep).
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.permissions import ModerationActor, can_moderate
from core.repositories.moderation_repo import moderation_repo
from core.scheduler import scheduler, in_seconds
from cogs.moderation._shared import (
    MODULE_ACTIONS,
    ensure_module_enabled,
    check_can_moderate,
    try_dm,
    parse_duration,
    format_duration,
    validate_reason,
    post_to_mod_log,
)
from core.premium import PremiumModule, registry

logger = logging.getLogger("iyokai.moderation.actions")

# action_type registrato nello scheduler per il tempban automatico.
# Costante qui perché serve sia a create_case (usa lo stesso testo
# come action_type del CASO, per coerenza nello storico) sia
# all'handler registrato in setup().
TEMPBAN_ACTION_TYPE = "tempban"
SCHEDULED_TEMPBAN_EXPIRE = "moderation_tempban_expire"

# Timeout nativo di Discord: massimo 28 giorni, oltre l'API rifiuta
# la richiesta. Lo controlliamo PRIMA di chiamare Discord per dare
# un messaggio chiaro invece di un errore HTTP criptico.
MAX_TIMEOUT_SECONDS = 28 * 86400


def _case_embed(
    title: str,
    color: discord.Color,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str | None,
    case_number: int,
    extra_field: tuple[str, str] | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Utente", value=f"{target.mention} ({target.id})", inline=False)
    embed.add_field(name="Moderatore", value=moderator.mention, inline=True)
    embed.add_field(name="Caso", value=f"#{case_number}", inline=True)
    if extra_field:
        embed.add_field(name=extra_field[0], value=extra_field[1], inline=True)
    embed.add_field(name="Motivo", value=reason or "Nessun motivo fornito", inline=False)
    return embed


class ModerationActionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # /warn
    # ================================================================
    @app_commands.command(name="warn", description="Assegna un warn a un membro.")
    @app_commands.describe(member="Il membro da avvisare", reason="Motivo del warn")
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="warn",
            reason=reason,
        )

        embed = _case_embed(
            "⚠️ Warn", discord.Color.yellow(), member, interaction.user, reason, case_number
        )
        await interaction.response.send_message(embed=embed)
        await try_dm(member, embed)
        await post_to_mod_log(interaction.guild, embed)

    # ================================================================
    # /kick
    # ================================================================
    @app_commands.command(name="kick", description="Espelle un membro dal server.")
    @app_commands.describe(member="Il membro da espellere", reason="Motivo dell'espulsione")
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        # Il DM va mandato PRIMA dell'azione: dopo il kick c'è ancora
        # un server in comune solo se il bot resta con l'utente in
        # altri server, quindi qui non è strettamente critico come
        # nel caso del ban (vedi spam trap), ma manteniamo comunque
        # l'ordine "notifica prima, azione dopo" per coerenza.
        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="kick",
            reason=reason,
        )
        embed = _case_embed(
            "👢 Kick", discord.Color.orange(), member, interaction.user, reason, case_number
        )
        dm_ok = await try_dm(member, embed)

        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per espellere questo utente.", ephemeral=True
            )
            return

        if not dm_ok:
            embed.set_footer(text="Non è stato possibile notificare l'utente in DM.")
        await interaction.response.send_message(embed=embed)
        await post_to_mod_log(interaction.guild, embed)

    # ================================================================
    # /ban
    # ================================================================
    @app_commands.command(name="ban", description="Banna permanentemente un membro.")
    @app_commands.describe(
        member="Il membro da bannare",
        reason="Motivo del ban",
        delete_message_days="Giorni di messaggi da cancellare (0-7, default 0)",
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
        delete_message_days: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="ban",
            reason=reason,
        )
        embed = _case_embed(
            "🔨 Ban", discord.Color.red(), member, interaction.user, reason, case_number
        )
        dm_ok = await try_dm(member, embed)

        try:
            await member.ban(
                reason=reason,
                delete_message_seconds=delete_message_days * 86400,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per bannare questo utente.", ephemeral=True
            )
            return

        if not dm_ok:
            embed.set_footer(text="Non è stato possibile notificare l'utente in DM.")
        await interaction.response.send_message(embed=embed)
        await post_to_mod_log(interaction.guild, embed)

    # ================================================================
    # /tempban
    # ================================================================
    @app_commands.command(
        name="tempban", description="Banna un membro per una durata definita."
    )
    @app_commands.describe(
        member="Il membro da bannare temporaneamente",
        duration="Durata, es. 7d, 12h, 30m",
        reason="Motivo del ban",
    )
    async def tempban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: str,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        try:
            duration_seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type=TEMPBAN_ACTION_TYPE,
            reason=reason,
            duration_seconds=duration_seconds,
        )

        embed = _case_embed(
            "⏳ Tempban",
            discord.Color.dark_red(),
            member,
            interaction.user,
            reason,
            case_number,
            extra_field=("Durata", format_duration(duration_seconds)),
        )
        dm_ok = await try_dm(member, embed)

        try:
            await member.ban(reason=reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per bannare questo utente.", ephemeral=True
            )
            return

        # Pianifica lo sblocco automatico. Il payload porta il
        # case_number, così l'handler può revocare il caso corretto
        # quando scade (vedi _handle_tempban_expire più sotto).
        await scheduler.schedule(
            guild_id=interaction.guild.id,
            user_id=member.id,
            action_type=SCHEDULED_TEMPBAN_EXPIRE,
            execute_at=in_seconds(duration_seconds),
            payload={"case_number": case_number},
        )

        if not dm_ok:
            embed.set_footer(text="Non è stato possibile notificare l'utente in DM.")
        await interaction.response.send_message(embed=embed)
        await post_to_mod_log(interaction.guild, embed)

    async def handle_tempban_expire(
        self, guild_id: int, user_id: int, payload: dict
    ) -> None:
        """
        Handler chiamato dallo scheduler quando un tempban scade.
        Registrato in setup() (vedi in fondo al file). Se il server
        non esiste più (bot rimosso) o l'utente non è più bannato
        (sbannato a mano nel frattempo), l'eccezione viene gestita
        dallo scheduler stesso: non marca l'azione come eseguita e
        la ritenta — MA qui gestiamo esplicitamente il caso "non è
        più bannato" come esito normale, non come errore, altrimenti
        verrebbe ritentato all'infinito inutilmente.
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            logger.warning(
                "Tempban scaduto per guild_id=%s ma il bot non è più in "
                "quel server: impossibile sbannare.",
                guild_id,
            )
            return

        try:
            await guild.unban(
                discord.Object(id=user_id), reason="Tempban scaduto automaticamente"
            )
        except discord.NotFound:
            # L'utente non risultava più bannato (già sbannato a
            # mano): non è un errore, è l'esito che ci aspettavamo.
            pass
        except discord.Forbidden:
            logger.error(
                "Permessi insufficienti per sbannare user_id=%s in "
                "guild_id=%s alla scadenza del tempban.",
                user_id,
                guild_id,
            )
            return

        case_number = payload.get("case_number")
        if case_number is not None:
            await moderation_repo.revoke_case(
                guild_id, case_number, revoked_by=self.bot.user.id
            )

    # ================================================================
    # /unban
    # ================================================================
    @app_commands.command(name="unban", description="Rimuove il ban da un utente.")
    @app_commands.describe(user_id="ID Discord dell'utente da sbannare", reason="Motivo dello sblocco")
    async def unban(
        self, interaction: discord.Interaction, user_id: str, reason: str
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID utente non valido.", ephemeral=True)
            return

        try:
            await interaction.guild.unban(discord.Object(id=uid), reason=reason)
        except discord.NotFound:
            await interaction.response.send_message(
                "Questo utente non risulta bannato.", ephemeral=True
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per sbannare questo utente.", ephemeral=True
            )
            return

        # Revoca l'ultimo caso attivo di tipo ban O tempban per
        # questo utente, qualunque dei due sia: get_latest_active_case
        # richiede un action_type preciso, quindi controlliamo
        # entrambi in ordine.
        for action_type in ("ban", TEMPBAN_ACTION_TYPE):
            case = await moderation_repo.get_latest_active_case(
                interaction.guild.id, uid, action_type
            )
            if case is not None:
                await moderation_repo.revoke_case(
                    interaction.guild.id, case.case_number, interaction.user.id
                )
                break

        await interaction.response.send_message(f"Utente `{uid}` sbannato.")
        log_embed = discord.Embed(title="🔓 Unban", color=discord.Color.green())
        log_embed.add_field(name="Utente", value=f"`{uid}`", inline=False)
        log_embed.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="Motivo", value=reason, inline=False)
        await post_to_mod_log(interaction.guild, log_embed)

    # ================================================================
    # /timeout e /untimeout
    # ================================================================
    @app_commands.command(
        name="timeout", description="Mette in timeout un membro (max 28 giorni)."
    )
    @app_commands.describe(
        member="Il membro da mettere in timeout",
        duration="Durata, es. 10m, 1h, 7d (massimo 28 giorni)",
        reason="Motivo del timeout",
    )
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: str,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        try:
            duration_seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        if duration_seconds > MAX_TIMEOUT_SECONDS:
            await interaction.response.send_message(
                "Il timeout nativo di Discord non può superare i 28 giorni. "
                "Per durate più lunghe usa /tempban se l'intento è "
                "allontanare l'utente dal server.",
                ephemeral=True,
            )
            return

        try:
            import datetime as _dt
            await member.timeout(
                _dt.timedelta(seconds=duration_seconds),
                reason=reason,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per mettere in timeout questo utente.",
                ephemeral=True,
            )
            return

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="timeout",
            reason=reason,
            duration_seconds=duration_seconds,
        )
        embed = _case_embed(
            "🔇 Timeout",
            discord.Color.dark_orange(),
            member,
            interaction.user,
            reason,
            case_number,
            extra_field=("Durata", format_duration(duration_seconds)),
        )
        await interaction.response.send_message(embed=embed)
        await try_dm(member, embed)
        await post_to_mod_log(interaction.guild, embed)

    @app_commands.command(
        name="untimeout", description="Rimuove il timeout da un membro."
    )
    @app_commands.describe(member="Il membro da cui rimuovere il timeout")
    async def untimeout(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return

        try:
            await member.timeout(None, reason="Timeout rimosso manualmente")
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per rimuovere il timeout da questo utente.",
                ephemeral=True,
            )
            return

        case = await moderation_repo.get_latest_active_case(
            interaction.guild.id, member.id, "timeout"
        )
        if case is not None:
            await moderation_repo.revoke_case(
                interaction.guild.id, case.case_number, interaction.user.id
            )

        await interaction.response.send_message(f"Timeout rimosso da {member.mention}.")


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_ACTIONS,
            display_name="Moderazione — Azioni base",
            description="Warn, kick, ban, tempban, timeout.",
            premium_capable=False,  # resta SEMPRE gratis, come da schema
        )
    )

    cog = ModerationActionsCog(bot)
    await bot.add_cog(cog)

    # Collega l'handler del tempban allo scheduler. Fatto qui e non
    # dentro il costruttore del cog: lo scheduler è uno stato globale
    # condiviso, registrarlo nel punto di caricamento del cog (setup)
    # è coerente con come core/scheduler.py descrive il pattern d'uso.
    scheduler.register_handler(
        SCHEDULED_TEMPBAN_EXPIRE, cog.handle_tempban_expire
    )
