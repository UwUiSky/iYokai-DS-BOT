"""
cogs/security/anti_nuke.py
==============================
Anti-Nuke (SPEC.md §7.2): rilevamento di azioni distruttive di massa
(cancellazione canali/ruoli, webhook, emoji/sticker, mass ban/kick)
ed intervento automatico sull'autore, più recovery best-effort e
alert allo staff. Modulo CANDIDATO PREMIUM, come Anti-Raid.

L'autore di un evento non è mai nel payload dell'evento gateway
stesso (Discord non lo include) — va sempre risolto via audit log
(`guild.audit_logs`), stesso approccio già usato in
`cogs/security/spam_trap.py` per il cleanup di webhook/inviti.

Recovery: `on_guild_channel_delete`/`on_guild_role_delete` ricevono
l'oggetto come l'ultima volta che era nella cache del client, PRIMA
della rimozione — permette di ricreare canale/ruolo con lo stesso
nome/permessi/posizione senza dover mantenere uno snapshot separato.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_logic import (
    AntiNukeConfig,
    NUKE_CATEGORY_BAN_KICK,
    NUKE_CATEGORY_CHANNEL,
    NUKE_CATEGORY_EMOJI,
    NUKE_CATEGORY_ROLE,
    NUKE_CATEGORY_WEBHOOK,
    category_max_count,
    category_window_seconds,
    is_nuke_violation,
)
from core.security_rate_tracker import security_rate_tracker
from cogs.moderation._shared import ensure_module_enabled, try_dm

logger = logging.getLogger("iyokai.anti_nuke")

MODULE_ANTI_NUKE = "anti_nuke"

# Finestra di ricerca nell'audit log: l'evento gateway e la riga di
# audit log corrispondente arrivano quasi sempre entro pochi secondi
# l'uno dall'altro, ma non sono garantiti nello stesso istante.
_AUDIT_LOG_LOOKBACK_SECONDS = 10


def _replace(settings: SecuritySettings, **overrides) -> SecuritySettings:
    dati = {
        "guild_id": settings.guild_id,
        "anti_raid": settings.anti_raid,
        "anti_nuke": settings.anti_nuke,
        "quarantine_role_id": settings.quarantine_role_id,
        "alert_channel_id": settings.alert_channel_id,
    }
    anti_nuke_fields = set(AntiNukeConfig.__dataclass_fields__.keys())
    anti_nuke_overrides = {k: v for k, v in overrides.items() if k in anti_nuke_fields}
    altri_overrides = {k: v for k, v in overrides.items() if k not in anti_nuke_fields}

    if anti_nuke_overrides:
        dati["anti_nuke"] = AntiNukeConfig(
            **{**{f: getattr(settings.anti_nuke, f) for f in anti_nuke_fields}, **anti_nuke_overrides}
        )
    dati.update(altri_overrides)
    return SecuritySettings(**dati)


async def _resolve_actor(guild: discord.Guild, action: discord.AuditLogAction, target_id: int | None = None) -> int | None:
    """
    Cerca nell'audit log la voce più recente per questa azione
    (opzionalmente filtrata per target) entro la finestra di
    tolleranza. None se non trovata o se il bot non ha i permessi
    per leggere l'audit log — mai un'eccezione che blocchi l'evento.
    """
    now = discord.utils.utcnow()
    try:
        async for entry in guild.audit_logs(action=action, limit=10):
            if (now - entry.created_at).total_seconds() > _AUDIT_LOG_LOOKBACK_SECONDS:
                break
            if target_id is not None and getattr(entry.target, "id", None) != target_id:
                continue
            return entry.user_id
    except discord.Forbidden:
        return None
    return None


async def _punish_actor(guild: discord.Guild, actor_id: int, config: AntiNukeConfig, reason: str) -> str:
    """Restituisce una descrizione di cosa è stato fatto, per il log/alert."""
    if guild.owner_id == actor_id:
        return "nessuna azione: l'autore è il proprietario del server"

    member = guild.get_member(actor_id)
    if member is None:
        return "nessuna azione: l'autore non è (più) un membro del server"

    if config.punish_action == "ban":
        try:
            await member.ban(reason=reason, delete_message_seconds=0)
            return f"{member} bannato"
        except discord.HTTPException:
            return f"tentativo di ban di {member} fallito (permessi insufficienti?)"

    try:
        await member.edit(roles=[], reason=reason)
        return f"tutti i ruoli rimossi da {member}"
    except discord.HTTPException:
        return f"tentativo di rimuovere i ruoli di {member} fallito (permessi insufficienti?)"


async def _alert_staff(guild: discord.Guild, settings: SecuritySettings, embed: discord.Embed) -> None:
    if guild.owner is not None:
        await try_dm(guild.owner, embed)
    if settings.alert_channel_id is not None:
        canale = guild.get_channel(settings.alert_channel_id)
        if isinstance(canale, discord.TextChannel):
            try:
                await canale.send(embed=embed)
            except discord.HTTPException:
                pass


class AntiNukeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    anti_nuke_group = app_commands.Group(
        name="anti-nuke", description="Configura la protezione anti-nuke del server."
    )

    @anti_nuke_group.command(name="enable", description="Attiva o disattiva l'Anti-Nuke.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def enable(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, enabled=enabled))
        await interaction.response.send_message(f"Anti-Nuke {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_nuke_group.command(name="limits", description="Configura la soglia di rilevamento per una categoria.")
    @app_commands.describe(max_actions="Numero massimo di azioni consentite nella finestra", seconds="Finestra in secondi")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Canali", value=NUKE_CATEGORY_CHANNEL),
            app_commands.Choice(name="Ruoli", value=NUKE_CATEGORY_ROLE),
            app_commands.Choice(name="Webhook", value=NUKE_CATEGORY_WEBHOOK),
            app_commands.Choice(name="Emoji/Sticker", value=NUKE_CATEGORY_EMOJI),
            app_commands.Choice(name="Ban/Kick", value=NUKE_CATEGORY_BAN_KICK),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def limits(
        self, interaction: discord.Interaction, category: app_commands.Choice[str], max_actions: int, seconds: int
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        campo_max = {
            NUKE_CATEGORY_CHANNEL: "channel_max", NUKE_CATEGORY_ROLE: "role_max",
            NUKE_CATEGORY_WEBHOOK: "webhook_max", NUKE_CATEGORY_EMOJI: "emoji_max",
            NUKE_CATEGORY_BAN_KICK: "ban_kick_max",
        }[category.value]
        campo_finestra = {
            NUKE_CATEGORY_CHANNEL: "channel_window_seconds", NUKE_CATEGORY_ROLE: "role_window_seconds",
            NUKE_CATEGORY_WEBHOOK: "webhook_window_seconds", NUKE_CATEGORY_EMOJI: "emoji_window_seconds",
            NUKE_CATEGORY_BAN_KICK: "ban_kick_window_seconds",
        }[category.value]
        await security_repo.save_settings(
            _replace(settings, **{campo_max: max_actions, campo_finestra: seconds})
        )
        await interaction.response.send_message(
            f"Soglia **{category.name}** impostata a {max_actions} ogni {seconds}s.", ephemeral=True
        )

    @anti_nuke_group.command(name="trusted-add", description="Esenta un utente/bot fidato da tutti i controlli Anti-Nuke.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def trusted_add(self, interaction: discord.Interaction, user_id: str) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        try:
            id_utente = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID utente non valido.", ephemeral=True)
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if id_utente not in settings.anti_nuke.trusted_ids:
            await security_repo.save_settings(
                _replace(settings, trusted_ids=settings.anti_nuke.trusted_ids + (id_utente,))
            )
        await interaction.response.send_message(f"Utente `{id_utente}` esentato dai controlli Anti-Nuke.", ephemeral=True)

    @anti_nuke_group.command(name="trusted-remove", description="Rimuove un utente/bot dalla lista fidati Anti-Nuke.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def trusted_remove(self, interaction: discord.Interaction, user_id: str) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        try:
            id_utente = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID utente non valido.", ephemeral=True)
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(
            _replace(settings, trusted_ids=tuple(i for i in settings.anti_nuke.trusted_ids if i != id_utente))
        )
        await interaction.response.send_message(f"Utente `{id_utente}` rimosso dalla lista fidati.", ephemeral=True)

    @anti_nuke_group.command(name="punish-action", description="Cosa fare all'autore di un'azione distruttiva di massa.")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Rimuovi tutti i ruoli", value="strip_roles"),
            app_commands.Choice(name="Banna", value="ban"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def punish_action(self, interaction: discord.Interaction, action: app_commands.Choice[str]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, punish_action=action.value))
        await interaction.response.send_message(f"Azione punitiva impostata su **{action.name}**.", ephemeral=True)

    @anti_nuke_group.command(name="recovery", description="Attiva/disattiva la ricreazione automatica di canali/ruoli cancellati durante un attacco.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def recovery(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, recovery_enabled=enabled))
        await interaction.response.send_message(f"Recovery automatico {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_nuke_group.command(name="status", description="Mostra la configurazione attuale dell'Anti-Nuke.")
    async def status(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        n = settings.anti_nuke
        righe = [
            f"**Attivo**: {'sì' if n.enabled else 'no'}",
            f"**Canali**: max {n.channel_max}/{n.channel_window_seconds}s",
            f"**Ruoli**: max {n.role_max}/{n.role_window_seconds}s",
            f"**Webhook**: max {n.webhook_max}/{n.webhook_window_seconds}s",
            f"**Emoji/Sticker**: max {n.emoji_max}/{n.emoji_window_seconds}s",
            f"**Ban/Kick**: max {n.ban_kick_max}/{n.ban_kick_window_seconds}s",
            f"**Azione punitiva**: {n.punish_action}",
            f"**Recovery automatico**: {'sì' if n.recovery_enabled else 'no'}",
            f"**Utenti fidati**: {len(n.trusted_ids)}",
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    # ================================================================
    # Motore di rilevamento — un metodo condiviso per ogni categoria,
    # così la logica "conta -> valuta -> punisci -> logga -> alert" non
    # si ripete cinque volte quasi identica.
    # ================================================================
    async def _handle_event(
        self, guild: discord.Guild, category: str, actor_id: int | None, detail_suffix: str
    ) -> SecuritySettings | None:
        if not await db.is_module_active_for_guild(guild.id, MODULE_ANTI_NUKE):
            return None
        settings = await security_repo.get_settings(guild.id)
        if not settings.anti_nuke.enabled or actor_id is None:
            return None

        now = discord.utils.utcnow()
        finestra = category_window_seconds(category, settings.anti_nuke)
        conteggio = security_rate_tracker.record_and_count(guild.id, actor_id, category, now, finestra)

        if not is_nuke_violation(actor_id, category, conteggio, settings.anti_nuke):
            return None

        esito = await _punish_actor(
            guild, actor_id, settings.anti_nuke, reason=f"Anti-Nuke: {category} — {detail_suffix}"
        )
        dettaglio = f"{detail_suffix} — {conteggio} azioni in {finestra}s — {esito}"
        await security_repo.log_action(guild.id, f"nuke_{category}", actor_id, dettaglio)

        embed = discord.Embed(
            title=f"🚨 Anti-Nuke — {category}", description=dettaglio, color=discord.Color.red()
        )
        await _alert_staff(guild, settings, embed)
        return settings

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        actor_id = await _resolve_actor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        await self._handle_event(channel.guild, NUKE_CATEGORY_CHANNEL, actor_id, f"creato #{channel.name}")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        actor_id = await _resolve_actor(channel.guild, discord.AuditLogAction.channel_delete)
        settings = await self._handle_event(channel.guild, NUKE_CATEGORY_CHANNEL, actor_id, f"cancellato #{channel.name}")

        if settings is not None and settings.anti_nuke.recovery_enabled:
            try:
                await channel.guild.create_text_channel(
                    name=channel.name,
                    category=getattr(channel, "category", None),
                    overwrites=getattr(channel, "overwrites", None),
                    reason="Anti-Nuke: recovery automatico dopo cancellazione di massa",
                ) if isinstance(channel, discord.TextChannel) else None
            except discord.HTTPException:
                logger.warning("Recovery del canale %s fallita.", channel.name)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        actor_id = await _resolve_actor(role.guild, discord.AuditLogAction.role_create, role.id)
        await self._handle_event(role.guild, NUKE_CATEGORY_ROLE, actor_id, f"creato ruolo {role.name}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        actor_id = await _resolve_actor(role.guild, discord.AuditLogAction.role_delete)
        settings = await self._handle_event(role.guild, NUKE_CATEGORY_ROLE, actor_id, f"cancellato ruolo {role.name}")

        if settings is not None and settings.anti_nuke.recovery_enabled:
            try:
                await role.guild.create_role(
                    name=role.name,
                    permissions=role.permissions,
                    colour=role.colour,
                    hoist=role.hoist,
                    mentionable=role.mentionable,
                    reason="Anti-Nuke: recovery automatico dopo cancellazione di massa",
                )
            except discord.HTTPException:
                logger.warning("Recovery del ruolo %s fallita.", role.name)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        actor_id = await _resolve_actor(channel.guild, discord.AuditLogAction.webhook_create)
        if actor_id is None:
            actor_id = await _resolve_actor(channel.guild, discord.AuditLogAction.webhook_delete)
        await self._handle_event(channel.guild, NUKE_CATEGORY_WEBHOOK, actor_id, f"webhook modificati in #{channel.name}")

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after) -> None:
        # Soundboard non incluso: discord.py 2.7 non esporrebbe un
        # evento gateway dedicato per le sound board (limite della
        # libreria/versione, non una scelta di scope) — emoji e
        # sticker (sotto) restano coperti.
        azione = discord.AuditLogAction.emoji_create if len(after) > len(before) else discord.AuditLogAction.emoji_delete
        actor_id = await _resolve_actor(guild, azione)
        await self._handle_event(guild, NUKE_CATEGORY_EMOJI, actor_id, "emoji del server modificate")

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before, after) -> None:
        azione = discord.AuditLogAction.sticker_create if len(after) > len(before) else discord.AuditLogAction.sticker_delete
        actor_id = await _resolve_actor(guild, azione)
        await self._handle_event(guild, NUKE_CATEGORY_EMOJI, actor_id, "sticker del server modificati")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User) -> None:
        actor_id = await _resolve_actor(guild, discord.AuditLogAction.ban, user.id)
        await self._handle_event(guild, NUKE_CATEGORY_BAN_KICK, actor_id, f"ban di {user}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        # on_member_remove scatta anche per un leave volontario — va
        # verificato nell'audit log se si tratta DAVVERO di un kick
        # prima di contarlo, altrimenti ogni utente che lascia il
        # server da solo alimenterebbe per errore il contatore.
        actor_id = await _resolve_actor(member.guild, discord.AuditLogAction.kick, member.id)
        if actor_id is None:
            return
        await self._handle_event(member.guild, NUKE_CATEGORY_BAN_KICK, actor_id, f"kick di {member}")


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_ANTI_NUKE,
            display_name="Anti-Nuke",
            category="security",
            description="Rilevamento e risposta automatica ad azioni distruttive di massa sul server.",
            premium_capable=True,
        )
    )
    await bot.add_cog(AntiNukeCog(bot))
