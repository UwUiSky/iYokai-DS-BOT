"""
cogs/security/anti_raid.py
==============================
Anti-Raid (SPEC.md §7.1): rilevamento di un'ondata di join sospetti
(join rate limit, età account, pattern username/avatar) e risposta
automatica (quarantena e/o innalzamento del livello di verifica),
più alert allo staff. Modulo CANDIDATO PREMIUM (come Spam Trap,
§7.3): protezione avanzata del server.

Logica di valutazione PURA in core/security_logic.py — qui solo
l'estrazione dei segnali dal `discord.Member` reale e l'esecuzione
della risposta (assegnazione ruolo quarantena, innalzamento
verification_level, alert, log).
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_logic import AntiRaidConfig, JoinSignals, evaluate_join
from core.security_rate_tracker import GUILD_WIDE_KEY, security_rate_tracker
from cogs.moderation._shared import ensure_module_enabled, try_dm

logger = logging.getLogger("iyokai.anti_raid")

MODULE_ANTI_RAID = "anti_raid"


async def _get_or_create_quarantine_role(
    guild: discord.Guild, settings: SecuritySettings
) -> discord.Role | None:
    """
    Stesso schema di `_get_or_create_mute_role` in
    cogs/moderation/softban_mute.py (ruolo dedicato + overwrite su
    ogni canale), ma un ruolo SEPARATO: la quarantena è per un
    sospetto raider appena entrato, il mute è per un membro esistente
    sanzionato — mescolarli renderebbe impossibile distinguere i due
    casi nell'audit trail del server.
    """
    if settings.quarantine_role_id is not None:
        role = guild.get_role(settings.quarantine_role_id)
        if role is not None:
            return role

    try:
        role = await guild.create_role(
            name="Quarantined", reason="Ruolo di quarantena creato automaticamente da iYokai (Anti-Raid)"
        )
    except discord.Forbidden:
        return None

    for channel in guild.channels:
        try:
            if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                await channel.set_permissions(
                    role, send_messages=False, add_reactions=False, reason="Setup ruolo quarantena"
                )
            elif isinstance(channel, discord.VoiceChannel):
                await channel.set_permissions(role, speak=False, connect=False, reason="Setup ruolo quarantena")
        except discord.HTTPException:
            logger.warning(
                "Impossibile impostare l'overwrite quarantena sul canale %s (server %s).",
                channel.id, guild.id,
            )

    nuova = _replace(settings, quarantine_role_id=role.id)
    await security_repo.save_settings(nuova)
    return role


def _replace(settings: SecuritySettings, **overrides) -> SecuritySettings:
    dati = {
        "guild_id": settings.guild_id,
        "anti_raid": settings.anti_raid,
        "anti_nuke": settings.anti_nuke,
        "quarantine_role_id": settings.quarantine_role_id,
        "alert_channel_id": settings.alert_channel_id,
    }
    anti_raid_fields = set(AntiRaidConfig.__dataclass_fields__.keys())
    anti_raid_overrides = {k: v for k, v in overrides.items() if k in anti_raid_fields}
    altri_overrides = {k: v for k, v in overrides.items() if k not in anti_raid_fields}

    if anti_raid_overrides:
        dati["anti_raid"] = AntiRaidConfig(
            **{**{f: getattr(settings.anti_raid, f) for f in anti_raid_fields}, **anti_raid_overrides}
        )
    dati.update(altri_overrides)
    return SecuritySettings(**dati)


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


class AntiRaidCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    anti_raid_group = app_commands.Group(
        name="anti-raid", description="Configura la protezione anti-raid del server."
    )

    @anti_raid_group.command(name="enable", description="Attiva o disattiva l'Anti-Raid.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def enable(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, enabled=enabled))
        await interaction.response.send_message(f"Anti-Raid {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_raid_group.command(name="join-rate", description="Configura il limite di join in un intervallo di tempo.")
    @app_commands.describe(max_joins="Numero massimo di join consentiti nella finestra", seconds="Finestra in secondi")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def join_rate(self, interaction: discord.Interaction, max_joins: int, seconds: int) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(
            _replace(settings, join_rate_max=max_joins, join_rate_window_seconds=seconds)
        )
        await interaction.response.send_message(f"Join rate limit impostato a {max_joins} ogni {seconds}s.", ephemeral=True)

    @anti_raid_group.command(name="account-age", description="Età minima dell'account per non essere considerato sospetto.")
    @app_commands.describe(seconds="Età minima in secondi (es. 86400 = 1 giorno)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def account_age(self, interaction: discord.Interaction, seconds: int) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, min_account_age_seconds=seconds))
        await interaction.response.send_message(f"Età minima account impostata a {seconds} secondi.", ephemeral=True)

    @anti_raid_group.command(name="username-check", description="Attiva/disattiva il rilevamento pattern username sospetti.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def username_check(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, check_username_pattern=enabled))
        await interaction.response.send_message(f"Rilevamento pattern username {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_raid_group.command(name="avatar-check", description="Attiva/disattiva il rilevamento avatar assente.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def avatar_check(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, check_avatar_pattern=enabled))
        await interaction.response.send_message(f"Rilevamento avatar assente {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_raid_group.command(name="lockdown-action", description="Cosa fare quando un raid viene rilevato.")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Quarantena (ruolo dedicato)", value="quarantine"),
            app_commands.Choice(name="Innalza il livello di verifica del server", value="verification"),
            app_commands.Choice(name="Entrambe", value="both"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def lockdown_action(self, interaction: discord.Interaction, action: app_commands.Choice[str]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, lockdown_action=action.value))
        await interaction.response.send_message(f"Azione di lockdown impostata su **{action.name}**.", ephemeral=True)

    @anti_raid_group.command(name="alert-channel", description="Canale dove ricevere gli alert di sicurezza (Anti-Raid + Anti-Nuke).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def alert_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, alert_channel_id=channel.id))
        await interaction.response.send_message(f"Canale di alert impostato su {channel.mention}.", ephemeral=True)

    @anti_raid_group.command(name="status", description="Mostra la configurazione attuale dell'Anti-Raid.")
    async def status(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        r = settings.anti_raid
        righe = [
            f"**Attivo**: {'sì' if r.enabled else 'no'}",
            f"**Join rate**: max {r.join_rate_max} ogni {r.join_rate_window_seconds}s",
            f"**Età minima account**: {r.min_account_age_seconds}s",
            f"**Controllo username**: {'sì' if r.check_username_pattern else 'no'}",
            f"**Controllo avatar**: {'sì' if r.check_avatar_pattern else 'no'}",
            f"**Azione di lockdown**: {r.lockdown_action}",
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if not await db.is_module_active_for_guild(guild.id, MODULE_ANTI_RAID):
            return

        settings = await security_repo.get_settings(guild.id)
        if not settings.anti_raid.enabled:
            return

        now = discord.utils.utcnow()
        conteggio = security_rate_tracker.record_and_count(
            guild.id, GUILD_WIDE_KEY, "joins", now, settings.anti_raid.join_rate_window_seconds
        )

        segnali = JoinSignals(
            account_created_at=member.created_at,
            has_avatar=member.avatar is not None,
            username=member.name,
            recent_join_count=conteggio,
        )
        violazioni = evaluate_join(segnali, settings.anti_raid, now)
        if not violazioni:
            return

        azione = settings.anti_raid.lockdown_action
        if azione in ("quarantine", "both"):
            ruolo = await _get_or_create_quarantine_role(guild, settings)
            if ruolo is not None:
                try:
                    await member.add_roles(ruolo, reason="Anti-Raid: join sospetto")
                except discord.HTTPException:
                    pass
                # Il ruolo potrebbe essere stato appena CREATO da
                # _get_or_create_quarantine_role: ricarichiamo le
                # settings per non sovrascrivere il quarantine_role_id
                # appena salvato con la copia "vecchia" già in mano.
                settings = await security_repo.get_settings(guild.id)

        if azione in ("verification", "both"):
            try:
                await guild.edit(
                    verification_level=discord.VerificationLevel.highest,
                    reason="Anti-Raid: ondata di join sospetti rilevata",
                )
            except discord.HTTPException:
                pass

        dettaglio = f"{member} — violazioni: {', '.join(violazioni)}"
        await security_repo.log_action(guild.id, "raid_join", member.id, dettaglio)

        embed = discord.Embed(
            title="🚨 Anti-Raid — join sospetto rilevato",
            description=dettaglio,
            color=discord.Color.red(),
        )
        await _alert_staff(guild, settings, embed)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_ANTI_RAID,
            display_name="Anti-Raid",
            category="security",
            description="Rilevamento e risposta automatica a ondate di join sospetti.",
            premium_capable=True,
        )
    )
    await bot.add_cog(AntiRaidCog(bot))
