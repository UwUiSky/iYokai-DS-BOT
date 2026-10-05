"""
cogs/utility/feed_alerts.py
==============================
Comandi di Custom RSS/Alert (SPEC.md §10.3, §10.7, §10.8, §10.9). Il
polling vero vive in core/feed_watcher.py (servizio bot-wide, non
legato a questo cog) — qui solo /alerts add|remove|list per
gestire le sottoscrizioni.
"""

# DA FARE (issue #67, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §11 (Feed e alert).
# DA FARE (issue #103, fase F13): NF-32, Alert: Kick, ruolo "in
#   diretta", TikTok, Instagram e X. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.custom_webhook_logic import build_webhook_url
from core.database import db
from core.repositories.custom_webhook_repo import custom_webhook_repo
from core.repositories.feed_subscription_repo import feed_subscription_repo
from core.repositories.twitch_subscription_repo import twitch_subscription_repo
from core.repositories.youtube_subscription_repo import youtube_subscription_repo
from core.premium import PremiumModule, registry
from core.safe_http import url_e_sicuro

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

        # BUG-20: stesso controllo che fa lo scaricamento vero
        # (core/safe_http.py) — un URL che non verrebbe mai letto va
        # rifiutato subito, non salvato. Il controllo risolve il nome
        # host e può superare i 3 secondi di Discord: prima il defer.
        await interaction.response.defer(ephemeral=True)
        if not await url_e_sicuro(feed_url):
            await interaction.followup.send(
                "⚠️ URL non valido o non raggiungibile. Deve iniziare con `http://` o "
                "`https://`, usare la porta standard (80 o 443) e puntare a un sito "
                "pubblico: indirizzi interni o locali non sono ammessi. Controlla di "
                "averlo copiato per intero e riprova.",
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

        await interaction.followup.send(
            f"✅ Sottoscrizione creata (ID `RSS-{subscription_id}`): notificherò in "
            f"{channel.mention} i nuovi contenuti da **{label}**. "
            f"Il primo controllo (entro 5 minuti) memorizza solo lo stato attuale, "
            f"non pubblica lo storico esistente.",
            ephemeral=True,
        )

    @alerts_group.command(
        name="webhook-create",
        description="[Admin] Crea un webhook custom: servizi terzi possono pubblicare in un canale.",
    )
    @app_commands.describe(
        channel="Canale dove pubblicare i messaggi ricevuti",
        label="Nome descrittivo, usato nel messaggio",
        message_template=(
            "Template personalizzato (facoltativo). Placeholder: {label} {title} {message} {url}"
        ),
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def webhook_create(
        self,
        interaction: discord.Interaction,
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

        webhook = await custom_webhook_repo.create_webhook(
            guild_id=guild.id,
            channel_id=channel.id,
            label=label,
            created_by=interaction.user.id,
            message_template=message_template,
        )

        if config.ALERTS_WEBHOOK_PUBLIC_BASE_URL:
            url = build_webhook_url(config.ALERTS_WEBHOOK_PUBLIC_BASE_URL, webhook.token)
            corpo_url = (
                f"URL: `{url}`\n\n"
                f"Manda una richiesta POST con un corpo JSON a questo URL "
                f"(es. `{{\"message\": \"testo\"}}`, campi opzionali: `title`, `url`) "
                f"e pubblicherò il messaggio in {channel.mention}."
            )
        else:
            corpo_url = (
                f"Token: `{webhook.token}`\n\n"
                f"⚠️ Nessun dominio configurato su questa istanza "
                f"(ALERTS_WEBHOOK_PUBLIC_BASE_URL) — chiedi all'amministratore del bot di "
                f"configurarne uno. Il percorso da esporre dietro quel dominio è "
                f"`/webhook/{webhook.token}`."
            )

        # SEC-14: il server webhook parte solo se ne esiste già almeno
        # uno all'avvio del bot — se questo è il primo mai creato, il
        # server non è ancora in ascolto e serve un riavvio.
        avviso_riavvio = ""
        if not getattr(self.bot, "custom_webhook_server_running", False):
            avviso_riavvio = (
                "\n\n⚠️ Il server che riceve i webhook non è ancora attivo su questa "
                "istanza (è il primo webhook creato): chiedi all'amministratore del bot "
                "di riavviarlo perché questo URL/token funzioni."
            )

        await interaction.response.send_message(
            f"✅ Webhook creato (ID `WH-{webhook.id}`) per **{label}**.\n\n{corpo_url}\n\n"
            f"⚠️ Questo URL/token è SEGRETO: chiunque lo conosca può pubblicare in "
            f"{channel.mention}. Non lo mostrerò di nuovo — se lo perdi, crealo di nuovo "
            f"e rimuovi quello vecchio con /alerts remove."
            f"{avviso_riavvio}",
            ephemeral=True,
        )

    @alerts_group.command(
        name="remove", description="[Admin] Rimuove una sottoscrizione feed, Twitch o un webhook."
    )
    @app_commands.describe(
        subscription_id="ID con prefisso, es. RSS-3, TW-2 o WH-1 (vedi /alerts list)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove(self, interaction: discord.Interaction, subscription_id: str) -> None:
        guild = interaction.guild
        if guild is None:
            return

        prefisso, _, numero_testo = subscription_id.upper().partition("-")
        if not numero_testo.isdigit():
            await interaction.response.send_message(
                "Formato ID non valido. Usa il formato mostrato da /alerts list, "
                "es. RSS-3, TW-2 o WH-1.",
                ephemeral=True,
            )
            return
        numero = int(numero_testo)

        if prefisso == "RSS":
            rimossa = await feed_subscription_repo.remove_subscription(numero, guild.id)
        elif prefisso == "TW":
            rimossa = await twitch_subscription_repo.remove_subscription(numero, guild.id)
        elif prefisso == "YT":
            rimossa = await youtube_subscription_repo.remove_subscription(numero, guild.id)
        elif prefisso == "WH":
            rimossa = await custom_webhook_repo.remove_webhook(numero, guild.id)
        else:
            await interaction.response.send_message(
                "Prefisso non riconosciuto. Usa RSS-<numero>, TW-<numero>, YT-<numero> "
                "o WH-<numero> (vedi /alerts list).",
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
            f"✅ Sottoscrizione Twitch creata (ID `TW-{subscription_id}`): notificherò in "
            f"{channel.mention} quando **{label}** va live o termina la diretta.",
            ephemeral=True,
        )

    @alerts_group.command(
        name="add-youtube-live",
        description="[Admin] Notifica quando un canale YouTube va live (richiede YOUTUBE_API_KEY sul bot).",
    )
    @app_commands.describe(
        youtube_channel_id="ID del canale YouTube (es. 'UCxxxxxxxxxxxxxxxxxxxxxx', non l'URL)",
        channel="Canale dove pubblicare le notifiche",
        label="Nome descrittivo, usato nel messaggio",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_youtube_live(
        self,
        interaction: discord.Interaction,
        youtube_channel_id: str,
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

        subscription_id = await youtube_subscription_repo.add_subscription(
            guild_id=guild.id,
            channel_id=channel.id,
            youtube_channel_id=youtube_channel_id,
            label=label,
            created_by=interaction.user.id,
        )

        avviso_quota = (
            ""
            if config.YOUTUBE_API_KEY
            else (
                "\n\n⚠️ Nessuna YOUTUBE_API_KEY configurata sul bot (SPEC.md "
                "§10.4, quota a consumo — non abilitata di default): la "
                "sottoscrizione resta inattiva finché il proprietario del bot "
                "non la imposta."
            )
        )
        await interaction.response.send_message(
            f"✅ Sottoscrizione YouTube creata (ID `YT-{subscription_id}`): notificherò in "
            f"{channel.mention} quando **{label}** va live.{avviso_quota}",
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
        youtube_subs = await youtube_subscription_repo.list_subscriptions(guild.id)
        webhooks = await custom_webhook_repo.list_webhooks(guild.id)

        if not feed_subs and not twitch_subs and not youtube_subs and not webhooks:
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
        righe += [
            f"`YT-{s.id}` **{s.label}** (YouTube live: {s.youtube_channel_id}) → <#{s.channel_id}>"
            for s in youtube_subs
        ]
        righe += [
            # MAI il token qui: è il segreto che autentica chi può
            # pubblicare in quel canale, mostrato una sola volta alla
            # creazione (vedi webhook_create).
            f"`WH-{w.id}` **{w.label}** (webhook) → <#{w.channel_id}>"
            for w in webhooks
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
            category="utility",
            description="Notifiche automatiche da feed RSS/Atom (YouTube, Reddit, RSS generici).",
            premium_capable=False,
        )
    )
    await bot.add_cog(FeedAlertsCog(bot))
