"""
cogs/logging/basic_logs.py
=============================
Logging semplificato: join, leave, ban, unban, creazione/eliminazione
ruoli, cambi di ruolo sui membri. Modulo SEMPRE GRATUITO
(MODULE_LOGGING), come da schema — il log "completo" (messaggi
cancellati/modificati, che richiede il Message Content Intent) è
previsto più avanti, nella Security Suite completa.

Punto tecnico verificato prima di scrivere questo file: discord.py
NON registra un listener di un Cog per la sola convenzione del nome
`on_xxx` — serve il decorator esplicito `@commands.Cog.listener()`
su ognuno, altrimenti il metodo resta un normale metodo Python che
Discord non chiama mai. Verificato empiricamente (non assunto) prima
di scrivere tutti i listener sottostanti.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db

MODULE_LOGGING = "logging_basic"
SETTING_LOG_CHANNEL = "log_channel_id"


def diff_roles(
    before_role_ids: set[int], after_role_ids: set[int]
) -> tuple[set[int], set[int]]:
    """
    Calcola quali ruoli sono stati aggiunti e quali rimossi tra due
    istantanee di ruoli di un membro. Logica pura (solo insiemi di
    interi), testata separatamente da qualunque evento Discord reale.
    """
    added = after_role_ids - before_role_ids
    removed = before_role_ids - after_role_ids
    return added, removed


async def _get_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    """
    Restituisce il canale di log configurato per questo server, solo
    se il modulo è attivo E un canale è stato impostato E quel canale
    esiste ancora. In ogni altro caso restituisce None: i listener
    controllano questo valore e non fanno nulla se è None, senza mai
    sollevare un errore per un server che non ha configurato nulla —
    un evento Discord non ha nessuno a cui rispondere con un
    messaggio d'errore, a differenza di uno slash command.
    """
    enabled = await db.is_module_active_for_guild(guild.id, MODULE_LOGGING)
    if not enabled:
        return None

    channel_id = await db.get_guild_setting(guild.id, SETTING_LOG_CHANNEL)
    if channel_id is None:
        return None

    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None
    return channel


class BasicLogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Comandi di configurazione
    # ================================================================
    @app_commands.command(
        name="logs-setup", description="[Admin] Imposta il canale dei log del server."
    )
    @app_commands.describe(channel="Il canale dove verranno inviati i log")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_setup(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        await db.set_guild_setting(interaction.guild.id, SETTING_LOG_CHANNEL, channel.id)
        await interaction.response.send_message(
            f"I log verranno inviati in {channel.mention}. "
            f"Ricorda di attivare il modulo con /setup se non l'hai già fatto.",
            ephemeral=True,
        )

    @app_commands.command(
        name="logs-status", description="Mostra il canale di log configurato."
    )
    async def logs_status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        channel_id = await db.get_guild_setting(interaction.guild.id, SETTING_LOG_CHANNEL)
        if channel_id is None:
            await interaction.response.send_message(
                "Nessun canale di log configurato. Usa /logs-setup.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)
        testo = channel.mention if channel is not None else f"canale eliminato (ID {channel_id})"
        await interaction.response.send_message(
            f"Canale di log configurato: {testo}", ephemeral=True
        )

    # ================================================================
    # Membri
    # ================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        channel = await _get_log_channel(member.guild)
        if channel is None:
            return

        embed = discord.Embed(
            title="📥 Membro entrato",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Utente", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(
            name="Account creato il",
            value=discord.utils.format_dt(member.created_at, style="F"),
            inline=False,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """
        Copre sia chi esce volontariamente sia chi viene espulso: a
        livello di evento Discord non fornisce questa distinzione qui
        (serve interrogare l'audit log con una query separata, che
        aggiungerebbe un'altra chiamata API per ogni singola uscita —
        non ne vale la pena per un log "semplificato"). Un kick fatto
        con /kick di iYokai risulta già loggato con motivo e
        moderatore nel case system di Moderation: questo evento resta
        un log generico di presenza, non sostituisce quello.
        """
        channel = await _get_log_channel(member.guild)
        if channel is None:
            return

        embed = discord.Embed(
            title="📤 Membro uscito",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Utente", value=f"{member} ({member.id})", inline=False)
        if member.joined_at is not None:
            embed.add_field(
                name="Era nel server dal",
                value=discord.utils.format_dt(member.joined_at, style="F"),
                inline=False,
            )
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        channel = await _get_log_channel(guild)
        if channel is None:
            return

        embed = discord.Embed(
            title="🔨 Utente bannato",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Utente", value=f"{user} ({user.id})", inline=False)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        channel = await _get_log_channel(guild)
        if channel is None:
            return

        embed = discord.Embed(
            title="🔓 Utente sbannato",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Utente", value=f"{user} ({user.id})", inline=False)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        # Ci interessano solo i cambi di ruolo, per ora: nickname e
        # altri cambi minori restano fuori dal log "semplificato".
        before_ids = {role.id for role in before.roles}
        after_ids = {role.id for role in after.roles}
        if before_ids == after_ids:
            return

        added_ids, removed_ids = diff_roles(before_ids, after_ids)
        if not added_ids and not removed_ids:
            return

        channel = await _get_log_channel(after.guild)
        if channel is None:
            return

        embed = discord.Embed(
            title="🎭 Ruoli aggiornati",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Utente", value=f"{after.mention} ({after.id})", inline=False)
        if added_ids:
            embed.add_field(
                name="Aggiunti",
                value=", ".join(f"<@&{rid}>" for rid in added_ids),
                inline=False,
            )
        if removed_ids:
            embed.add_field(
                name="Rimossi",
                value=", ".join(f"<@&{rid}>" for rid in removed_ids),
                inline=False,
            )
        await channel.send(embed=embed)

    # ================================================================
    # Ruoli del server (creazione/eliminazione, non assegnazione)
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        channel = await _get_log_channel(role.guild)
        if channel is None:
            return

        embed = discord.Embed(
            title="➕ Ruolo creato",
            description=f"{role.mention} (`{role.name}`)",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        channel = await _get_log_channel(role.guild)
        if channel is None:
            return

        embed = discord.Embed(
            title="➖ Ruolo eliminato",
            description=f"`{role.name}`",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        await channel.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    from core.premium import PremiumModule, registry

    registry.register(
        PremiumModule(
            name=MODULE_LOGGING,
            display_name="Logging semplificato",
            description="Log di join/leave/ban/unban e modifiche ai ruoli.",
            premium_capable=False,
        )
    )
    await bot.add_cog(BasicLogsCog(bot))
