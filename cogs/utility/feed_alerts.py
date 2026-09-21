"""
cogs/utility/feed_alerts.py
==============================
Comandi di Custom RSS/Alert (SPEC.md §10.3, §10.7, §10.8, §10.9). Il
polling vero vive in core/feed_watcher.py (servizio bot-wide, non
legato a questo cog) — qui solo /alerts add|remove|list per
gestire le sottoscrizioni.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.repositories.feed_subscription_repo import feed_subscription_repo
from core.repositories.twitch_subscription_repo import twitch_subscription_repo
from core.premium import PremiumModule, registry

MODULE_FEED_ALERTS = "feed_alerts"


class FeedAlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    alerts_group = app_commands.Group(
        name="alerts", description="Notifiche automatiche da feed RSS/Atom esterni."
    )

    @alerts_group.command(
        name="add", description="[Admin] Segui un feed RSS/Atom (YouTube, Reddit, o qualsiasi altro)."
    )
    @app_commands.describe(
        feed_url="URL del feed RSS/Atom — es. youtube.com/feeds/videos.xml?channel_id=... o reddit.com/r/nome/new/.rss",
        channel="Canale dove pubblicare le notifiche",
        label="Nome descrittivo, usato nel messaggio (es. 'Canale YouTube di Mario')",
        message_template="Template personalizzato (facoltativo). Placeholder: {label} {title} {link}",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add(
        self,
        interaction: discord.Interaction,
        feed_url: str,
        channel: discord.TextChannel,
        label: str,
        message_template: str | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_FEED_ALERTS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return

        subscription_id = await feed_subscription_repo.add_subscription(
            guild_id=guild.id,
            channel_id=channel.id,
            feed_url=feed_url,
            label=label,
            created_by=interaction.user.id,
            message_template=message_template,
        )

        await interaction.response.send_message(
            f"✅ Sottoscrizione creata (ID `{subscription_id}`): notificherò in "
            f"{channel.mention} i nuovi contenuti da **{label}**. "
            f"Il primo controllo (entro 5 minuti) memorizza solo lo stato attuale, "
            f"non pubblica lo storico esistente.",
            ephemeral=True,
        )

    @alerts_group.command(name="remove", description="[Admin] Rimuove una sottoscrizione feed o Twitch.")
    @app_commands.describe(
        subscription_id="ID della sottoscrizione con prefisso, es. RSS-3 o TW-2 (vedi /alerts list)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove(self, interaction: discord.Interaction, subscription_id: str) -> None:
        guild = interaction.guild
        if guild is None:
            return

        prefisso, _, numero_testo = subscription_id.upper().partition("-")
        if not numero_testo.isdigit():
            await interaction.response.send_message(
                "Formato ID non valido. Usa il formato mostrato da /alerts list, es. RSS-3 o TW-2.",
                ephemeral=True,
            )
            return
        numero = int(numero_testo)

        if prefisso == "RSS":
            rimossa = await feed_subscription_repo.remove_subscription(numero, guild.id)
        elif prefisso == "TW":
            rimossa = await twitch_subscription_repo.remove_subscription(numero, guild.id)
        else:
            await interaction.response.send_message(
                "Prefisso non riconosciuto. Usa RSS-<numero> o TW-<numero> (vedi /alerts list).",
                ephemeral=True,
            )
            return

        if rimossa:
            await interaction.response.send_message("Sottoscrizione rimossa.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Nessuna sottoscrizione trovata con questo ID in questo server.",
                ephemeral=True,
            )

    @alerts_group.command(
        name="add-twitch", description="[Admin] Notifica quando uno streamer Twitch va live/offline."
    )
    @app_commands.describe(
        twitch_login="Nome utente Twitch (es. 'shroud', non l'URL completo)",
        channel="Canale dove pubblicare le notifiche",
        label="Nome descrittivo, usato nel messaggio",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_twitch(
        self,
        interaction: discord.Interaction,
        twitch_login: str,
        channel: discord.TextChannel,
        label: str,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_FEED_ALERTS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return

        subscription_id = await twitch_subscription_repo.add_subscription(
            guild_id=guild.id,
            channel_id=channel.id,
            twitch_login=twitch_login,
            label=label,
            created_by=interaction.user.id,
        )

        await interaction.response.send_message(
            f"✅ Sottoscrizione Twitch creata (ID `{subscription_id}`): notificherò in "
            f"{channel.mention} quando **{label}** va live o termina la diretta.",
            ephemeral=True,
        )

    @alerts_group.command(name="list", description="[Admin] Mostra i feed seguiti da questo server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_alerts(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        feed_subs = await feed_subscription_repo.list_subscriptions(guild.id)
        twitch_subs = await twitch_subscription_repo.list_subscriptions(guild.id)

        if not feed_subs and not twitch_subs:
            await interaction.response.send_message(
                "Nessuna sottoscrizione attiva su questo server.", ephemeral=True
            )
            return

        righe = [
            f"`RSS-{s.id}` **{s.label}** → <#{s.channel_id}>\n  {s.feed_url}"
            for s in feed_subs
        ]
        righe += [
            f"`TW-{s.id}` **{s.label}** (Twitch: {s.twitch_login}) → <#{s.channel_id}>"
            for s in twitch_subs
        ]
        embed = discord.Embed(
            title="🔔 Sottoscrizioni attive",
            description="\n".join(righe),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_FEED_ALERTS,
            display_name="Feed Alerts",
            description="Notifiche automatiche da feed RSS/Atom (YouTube, Reddit, RSS generici).",
            premium_capable=False,
        )
    )
    await bot.add_cog(FeedAlertsCog(bot))
