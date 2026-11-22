"""
cogs/utility/alert_piattaforme.py
=================================
Avvisi per piattaforme senza interfaccia dedicata, con /admin-alert: Bluesky, podcast, canale YouTube da
qualsiasi link, subreddit, feed noti di anime, manga e giochi gratis, Picarto. Tutti usano il motore dei feed
(controllo ogni 5 minuti, indirizzi sempre da `core/safe_http.py`) o il watcher delle dirette.
Funzioni coperte: SPEC §10.8, §10.13 (#129 ALR-006, 007, 008, 011, 012, 013, 014, 015, 016, 017)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import alert_piattaforme_logic as piat
from core.alert_limiti_logic import tetto_e_pieno
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.feed_alert_gate import MODULE_FEED_ALERTS
from core.i18n import testo_per
from core.picarto_watcher import picarto_watcher
from core.podcast_logic import Podcast, cerca_podcast
from core.repositories.alert_options_repo import alert_options_repo
from core.repositories.feed_subscription_repo import feed_subscription_repo
from core.repositories.picarto_subscription_repo import picarto_subscription_repo
from core.repositories.youtube_subscription_repo import youtube_subscription_repo
from core.controllo_link import e_link_pericoloso
from core.safe_http import url_e_sicuro
from core.twitch_eventi import twitch_eventi
from core.ui_base import BaseView
from core.youtube_link_logic import risolvi_canale

GRUPPO = "admin-alert"
PERMESSI_CANALE = ("view_channel", "send_messages", "embed_links")
URL_FEED_YOUTUBE = "https://www.youtube.com/feeds/videos.xml?channel_id={id}"
_NESSUNA = discord.AllowedMentions.none()


async def _pronto(interaction: discord.Interaction, canale: discord.TextChannel) -> bool:
    """Modulo acceso e bot in grado di scrivere nel canale; altrimenti risponde e dice False."""
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
        return False
    if not await db.is_module_active_for_guild(guild.id, MODULE_FEED_ALERTS):
        await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
        return False
    me = guild.me
    if me is None or canale.guild.id != guild.id or not all(getattr(canale.permissions_for(me), p) for p in PERMESSI_CANALE):
        await interaction.response.send_message(await testo_per(interaction, "alertgest_canale_senza_permessi", v1=canale.mention), ephemeral=True)
        return False
    return True


async def aggiungi_feed(
    interaction: discord.Interaction, url: str, canale: discord.TextChannel, label: str,
    *, formato: str | None = None, template: str | None = None, risposta: str | None = None,
) -> int | None:
    """Crea un feed del server (tetti, indirizzo sicuro). Risponde con il followup: `interaction` deve avere fatto defer."""
    guild = interaction.guild
    if not await url_e_sicuro(url) or await e_link_pericoloso(url):
        await interaction.followup.send(await testo_per(interaction, "alertplat_indirizzo_non_valido"), ephemeral=True)
        return None
    tetto, pieno = await tetto_e_pieno(guild.id, interaction.client)
    if pieno:
        await interaction.followup.send(await testo_per(interaction, "alertlim_totale_pieno"), ephemeral=True)
        return None
    numero = await feed_subscription_repo.add_subscription(
        guild_id=guild.id, channel_id=canale.id, feed_url=url, label=label, created_by=interaction.user.id,
        message_template=template, max_per_guild=tetto,
    )
    if numero is None:
        await interaction.followup.send(await testo_per(interaction, "feedalerts_questo_server_ha_gia_feed", v1=tetto), ephemeral=True)
        return None
    if formato:
        await alert_options_repo.set_fields("RSS", numero, guild.id, formato=formato)
    await interaction.followup.send(
        risposta or await testo_per(interaction, "alertplat_creato", v1=numero, v2=canale.mention, v3=label[:100]),
        ephemeral=True, allowed_mentions=_NESSUNA,
    )
    return numero


class _ScegliPodcast(BaseView):
    """Il menu con i podcast trovati: solo chi ha lanciato il comando sceglie (ALR-007)."""

    def __init__(self, autore_id: int, trovati: list[Podcast], canale: discord.TextChannel) -> None:
        super().__init__(timeout=120)
        self.autore_id, self.trovati, self.canale = autore_id, trovati, canale
        scelta = discord.ui.Select(
            placeholder="Scegli il podcast",
            options=[discord.SelectOption(label=p.nome[:100], description=(p.autore or "-")[:100], value=str(i)) for i, p in enumerate(trovati)],
        )
        scelta.callback = self._scelto
        self.add_item(scelta)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(await testo_per(interaction, "alertgest_solo_chi_ha_lanciato"), ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    async def _scelto(self, interaction: discord.Interaction) -> None:
        podcast = self.trovati[int(interaction.data["values"][0])]
        await interaction.response.defer(ephemeral=True)
        self.stop()
        await aggiungi_feed(interaction, podcast.feed_url, self.canale, podcast.nome[:100])


class AlertPiattaformeCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        picarto_watcher.start(self.bot)  # ALR-008
        twitch_eventi.start(self.bot)  # ALR-013

    async def cog_unload(self) -> None:
        picarto_watcher.stop()
        twitch_eventi.stop()
        await super().cog_unload()

    @comando_di_gruppo(GRUPPO, nome="bluesky", descrizione="Avvisa dei nuovi post di un profilo Bluesky.")
    @app_commands.describe(profilo="Il nome del profilo, es. nome.bsky.social", canale="Dove pubblicare", etichetta="Nome usato nel messaggio")
    async def bluesky(
        self, interaction: discord.Interaction, profilo: app_commands.Range[str, 3, 300],
        canale: discord.TextChannel, etichetta: app_commands.Range[str, 1, 100],
    ) -> None:
        """ALR-006: il profilo Bluesky ha un feed RSS; qui si costruisce l'indirizzo."""
        if not await _pronto(interaction, canale):
            return
        url = piat.indirizzo_bluesky(profilo)
        if url is None:
            await interaction.response.send_message(await testo_per(interaction, "alertplat_profilo_non_valido"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await aggiungi_feed(interaction, url, canale, etichetta, template="🦋 **{label}**: {title}\n{link}")

    @comando_di_gruppo(GRUPPO, nome="podcast", descrizione="Cerca un podcast per nome e avvisa dei nuovi episodi.")
    @app_commands.describe(nome="Il nome del podcast", canale="Dove pubblicare")
    async def podcast(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 2, 100], canale: discord.TextChannel
    ) -> None:
        """ALR-007: ricerca del feed e scelta tra i primi risultati."""
        if not await _pronto(interaction, canale):
            return
        await interaction.response.defer(ephemeral=True)
        trovati = await cerca_podcast(nome)
        if not trovati:
            await interaction.followup.send(await testo_per(interaction, "alertplat_podcast_non_trovato"), ephemeral=True)
            return
        await interaction.followup.send(
            await testo_per(interaction, "alertplat_podcast_scegli"), view=_ScegliPodcast(interaction.user.id, trovati, canale),
            ephemeral=True,
        )

    @comando_di_gruppo(GRUPPO, nome="youtube", descrizione="Aggiungi un canale YouTube da qualsiasi link: video, Short, @nome, playlist.")
    @app_commands.describe(
        link="Un link di YouTube (video, Short, canale, @nome, playlist) o l'ID del canale",
        canale="Dove pubblicare", etichetta="Nome usato nel messaggio",
        anche_live="Avvisa anche quando va in diretta (serve YOUTUBE_API_KEY del bot)",
    )
    async def youtube(
        self, interaction: discord.Interaction, link: app_commands.Range[str, 3, 300], canale: discord.TextChannel,
        etichetta: app_commands.Range[str, 1, 100], anche_live: bool = False,
    ) -> None:
        """ALR-011: ricava l'ID del canale dal link (una richiesta, solo ai siti di YouTube)."""
        if not await _pronto(interaction, canale):
            return
        await interaction.response.defer(ephemeral=True)
        id_canale = await risolvi_canale(link)
        if id_canale is None:
            await interaction.followup.send(await testo_per(interaction, "alertplat_youtube_non_trovato"), ephemeral=True)
            return
        numero = await aggiungi_feed(interaction, URL_FEED_YOUTUBE.format(id=id_canale), canale, etichetta)
        if numero is not None and anche_live:
            tetto, pieno = await tetto_e_pieno(interaction.guild.id, interaction.client)
            live = None if pieno else await youtube_subscription_repo.add_subscription(
                guild_id=interaction.guild.id, channel_id=canale.id, youtube_channel_id=id_canale, label=etichetta,
                created_by=interaction.user.id, max_per_guild=tetto,
            )
            await interaction.followup.send(
                await testo_per(interaction, "alertplat_live_creato" if live else "alertlim_totale_pieno", v1=live),
                ephemeral=True,
            )

    @comando_di_gruppo(GRUPPO, nome="subreddit", descrizione="Avvisa dei nuovi post di un subreddit, come testo o embed.")
    @app_commands.describe(
        nome="Il nome del subreddit, senza r/", canale="Dove pubblicare",
        formato="Come pubblicare i post", immagini="Solo subreddit sicuri di immagini e meme (ogni post come embed)",
    )
    @app_commands.choices(formato=[app_commands.Choice(name="testo", value="testo"), app_commands.Choice(name="embed", value="embed")])
    async def subreddit(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 3, 25], canale: discord.TextChannel,
        formato: app_commands.Choice[str] | None = None, immagini: bool = False,
    ) -> None:
        """ALR-014 (testo o embed) e ALR-016 (immagini e meme da un elenco di subreddit scelti)."""
        if not await _pronto(interaction, canale):
            return
        url = piat.indirizzo_subreddit(nome, solo_sicuri=immagini)
        if url is None:
            chiave = "alertplat_subreddit_non_ammesso" if immagini else "alertplat_subreddit_non_valido"
            await interaction.response.send_message(await testo_per(interaction, chiave, v1=", ".join(piat.SUBREDDIT_SICURI)), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        scelto = "embed" if immagini else (formato.value if formato else "testo")
        await aggiungi_feed(interaction, url, canale, "r/" + nome.strip().lower().removeprefix("r/")[:60], formato=scelto)

    @comando_di_gruppo(GRUPPO, nome="feed-noto", descrizione="Notizie di anime e manga o giochi gratis, da feed già scelti.")
    @app_commands.describe(argomento="Cosa seguire", canale="Dove pubblicare")
    @app_commands.choices(argomento=[app_commands.Choice(name=d[:100], value=k) for k, (_, d) in piat.FEED_NOTI.items()])
    async def feed_noto(
        self, interaction: discord.Interaction, argomento: app_commands.Choice[str], canale: discord.TextChannel
    ) -> None:
        """ALR-015 e ALR-017: feed pubblici scelti dall'owner; si usano senza copiare nessun indirizzo."""
        if not await _pronto(interaction, canale):
            return
        url, descrizione = piat.FEED_NOTI[argomento.value]
        await interaction.response.defer(ephemeral=True)
        await aggiungi_feed(interaction, url, canale, descrizione.split(" (")[0][:100])

    @comando_di_gruppo(GRUPPO, nome="picarto", descrizione="Avvisa quando un canale Picarto va in diretta.")
    @app_commands.describe(canale_picarto="Il nome del canale su Picarto", canale="Dove pubblicare", etichetta="Nome usato nel messaggio")
    async def picarto(
        self, interaction: discord.Interaction, canale_picarto: app_commands.Range[str, 2, 100],
        canale: discord.TextChannel, etichetta: app_commands.Range[str, 1, 100],
    ) -> None:
        """ALR-008: stesso schema di Kick; il controllo è una richiesta per canale, senza chiavi."""
        if not await _pronto(interaction, canale):
            return
        nome = piat.nome_picarto_valido(canale_picarto)
        if nome is None:
            await interaction.response.send_message(await testo_per(interaction, "alertplat_picarto_non_valido"), ephemeral=True)
            return
        tetto, pieno = await tetto_e_pieno(interaction.guild.id, interaction.client)
        numero = None if pieno else await picarto_subscription_repo.add_subscription(
            guild_id=interaction.guild.id, channel_id=canale.id, picarto_name=nome, label=etichetta,
            created_by=interaction.user.id, max_per_guild=tetto,
        )
        if numero is None:
            await interaction.response.send_message(await testo_per(interaction, "alertlim_totale_pieno"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "alertplat_picarto_creato", v1=numero, v2=canale.mention, v3=etichetta[:100]),
            ephemeral=True, allowed_mentions=_NESSUNA,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlertPiattaformeCog(bot))
