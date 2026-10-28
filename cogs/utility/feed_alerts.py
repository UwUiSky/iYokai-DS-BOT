"""
cogs/utility/feed_alerts.py
==============================
Comandi di Custom RSS/Alert (SPEC.md §10.3, §10.7, §10.8, §10.9, §10.13).
Il polling vero vive nei watcher di core/ (servizi bot-wide, non legati a
questo cog) — qui solo /moduli alert feed|twitch|youtube-live|kick|webhook|
opzioni|ruolo-live|guida-social|rimuovi|elenco per gestire le
sottoscrizioni e le loro opzioni.
"""

from __future__ import annotations

import os

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.alert_options_logic import (
    MAX_ATTESA_MINUTI,
    MAX_FILTRO,
    SIGLE_DIRETTA,
    AlertOptions,
    GUIDA_SOCIAL,
    profilo_social_senza_feed,
    leggi_id_avviso,
)
from core.config import config
from core.custom_webhook_logic import build_webhook_url
from core.database import db
from core.feed_alert_gate import MODULE_FEED_ALERTS
from core.kick_api_logic import normalizza_slug
from core.repositories.alert_options_repo import alert_options_repo
from core.repositories.custom_webhook_repo import custom_webhook_repo
from core.repositories.feed_subscription_repo import feed_subscription_repo
from core.repositories.kick_subscription_repo import kick_subscription_repo
from core.repositories.twitch_subscription_repo import twitch_subscription_repo
from core.repositories.youtube_subscription_repo import youtube_subscription_repo
from core.premium import PremiumModule, registry
from core.safe_http import url_e_sicuro


# LIM-16 (M 11.8): ogni feed e' uno scarico ogni 5 minuti.
MAX_FEED_PER_SERVER = 25
# Tetto per server anche per Twitch, YouTube e Kick (LIM-46: quota delle API).
MAX_LIVE_PER_SERVER = 25
SOTTOGRUPPO = ("alert", "Avvisi: feed, Twitch, YouTube, Kick")
# Un embed accetta 4096 caratteri nella descrizione; si lascia margine per la riga finale.
MAX_CARATTERI_ELENCO = 3900
MAX_CARATTERI_RIGA = 300


async def _tetto_raggiunto(interaction: discord.Interaction, servizio: str) -> None:
    await interaction.response.send_message(
        f"Questo server ha già {MAX_LIVE_PER_SERVER} avvisi {servizio}, il massimo consentito. "
        "Rimuovine uno con /moduli alert rimuovi prima di aggiungerne un altro.",
        ephemeral=True,
    )


def _elenco_tagliato(righe: list[str]) -> str:
    """Righe intere fino al tetto, poi 'e altre N' (la descrizione di un embed arriva a 4096)."""
    usate: list[str] = []
    lunghezza = 0
    for riga in righe:
        # Ogni riga inizia con l'ID: una riga lunghissima (URL) si tronca,
        # cosi' l'ID per rimuoverla si vede sempre.
        if len(riga) > MAX_CARATTERI_RIGA:
            riga = riga[: MAX_CARATTERI_RIGA - 1] + "…"
        if lunghezza + len(riga) + 1 > MAX_CARATTERI_ELENCO:
            break
        usate.append(riga)
        lunghezza += len(riga) + 1
    mancanti = len(righe) - len(usate)
    if mancanti:
        usate.append(f"… e altre {mancanti} sottoscrizioni.")
    return "\n".join(usate)


class FeedAlertsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "moduli",
        nome="feed",
        descrizione="Segui un feed RSS/Atom.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        feed_url="URL del feed RSS/Atom",
        channel="Dove pubblicare",
        label="Nome usato nel messaggio",
        message_template="Testo (facoltativo): {label} {title} {link}",
    )
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
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return

        # 10.5, 10.6, 10.13: la pagina di un profilo social non è un feed. Si spiega la strada regolare.
        if profilo_social_senza_feed(feed_url):
            await interaction.response.send_message(
                "Quella è la pagina di un profilo (TikTok, Instagram o X), non un feed: non posso leggerla. "
                "Serve l'indirizzo di un feed RSS «ponte» di un servizio esterno, oppure un webhook. "
                "Guarda `/moduli alert guida-social`.",
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
            max_per_guild=MAX_FEED_PER_SERVER,  # controllo e scrittura atomici
        )
        if subscription_id is None:
            await interaction.followup.send(
                f"Questo server ha già {MAX_FEED_PER_SERVER} feed, il massimo consentito. "
                "Rimuovine uno con /moduli alert rimuovi prima di aggiungerne un altro.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Sottoscrizione creata (ID `RSS-{subscription_id}`): notificherò in "
            f"{channel.mention} i nuovi contenuti da **{label}**. "
            f"Il primo controllo (entro 5 minuti) memorizza solo lo stato attuale, "
            f"non pubblica lo storico esistente.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "moduli",
        nome="webhook",
        descrizione="Crea un webhook per pubblicare da servizi esterni.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        channel="Dove pubblicare",
        label="Nome usato nel messaggio",
        message_template="Testo (facoltativo): {label} {title} {message} {url}",
    )
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
                "Un amministratore può attivarlo con /admin setup attiva.",
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
            f"e rimuovi quello vecchio con /moduli alert rimuovi."
            f"{avviso_riavvio}",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "moduli",
        nome="rimuovi",
        descrizione="Rimuove un avviso o un webhook.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        subscription_id="ID con prefisso, es. TW-2 o WH-1"
    )
    async def remove(self, interaction: discord.Interaction, subscription_id: str) -> None:
        guild = interaction.guild
        if guild is None:
            return

        prefisso, _, numero_testo = subscription_id.upper().partition("-")
        if not numero_testo.isdigit():
            await interaction.response.send_message(
                "Formato ID non valido. Usa il formato mostrato da /moduli alert elenco, "
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
        elif prefisso == "KK":
            rimossa = await kick_subscription_repo.remove_subscription(numero, guild.id)
        elif prefisso == "WH":
            rimossa = await custom_webhook_repo.remove_webhook(numero, guild.id)
        else:
            await interaction.response.send_message(
                "Prefisso non riconosciuto. Usa RSS-<numero>, TW-<numero>, YT-<numero>, "
                "KK-<numero> o WH-<numero> (vedi /moduli alert elenco).",
                ephemeral=True,
            )
            return

        if rimossa:
            if prefisso != "WH":
                await alert_options_repo.delete(prefisso, numero, guild.id)
            await interaction.response.send_message("Sottoscrizione rimossa.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Nessuna sottoscrizione trovata con questo ID in questo server.",
                ephemeral=True,
            )

    @comando_di_gruppo(
        "moduli",
        nome="twitch",
        descrizione="Avvisa quando uno streamer Twitch va live.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        twitch_login="Nome utente Twitch (non l'URL)",
        channel="Dove pubblicare",
        label="Nome usato nel messaggio",
    )
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
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return

        subscription_id = await twitch_subscription_repo.add_subscription(
            guild_id=guild.id,
            channel_id=channel.id,
            twitch_login=twitch_login,
            label=label,
            created_by=interaction.user.id,
            max_per_guild=MAX_LIVE_PER_SERVER,
        )
        if subscription_id is None:
            await _tetto_raggiunto(interaction, "Twitch")
            return

        await interaction.response.send_message(
            f"✅ Sottoscrizione Twitch creata (ID `TW-{subscription_id}`): notificherò in "
            f"{channel.mention} quando **{label}** va live o termina la diretta.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "moduli",
        nome="youtube-live",
        descrizione="Avvisa quando un canale YouTube va live.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        youtube_channel_id="ID del canale YouTube (UC…, non l'URL)",
        channel="Dove pubblicare",
        label="Nome usato nel messaggio",
    )
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
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return

        subscription_id = await youtube_subscription_repo.add_subscription(
            guild_id=guild.id,
            channel_id=channel.id,
            youtube_channel_id=youtube_channel_id,
            label=label,
            created_by=interaction.user.id,
            max_per_guild=MAX_LIVE_PER_SERVER,
        )
        if subscription_id is None:
            await _tetto_raggiunto(interaction, "YouTube")
            return

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

    @comando_di_gruppo(
        "moduli",
        nome="kick",
        descrizione="Avvisa quando un canale Kick va in diretta.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        kick="Nome del canale Kick o link",
        channel="Dove pubblicare",
        label="Nome usato nel messaggio",
    )
    async def add_kick(
        self,
        interaction: discord.Interaction,
        kick: app_commands.Range[str, 1, 100],
        channel: discord.TextChannel,
        label: app_commands.Range[str, 1, 100],
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
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return
        slug = normalizza_slug(kick)
        if slug is None:
            await interaction.response.send_message(
                "Nome del canale Kick non valido: usa solo lettere, numeri, `_` e `-` "
                "(oppure il link kick.com/nome).",
                ephemeral=True,
            )
            return

        subscription_id = await kick_subscription_repo.add_subscription(
            guild_id=guild.id,
            channel_id=channel.id,
            kick_slug=slug,
            label=label,
            created_by=interaction.user.id,
            max_per_guild=MAX_LIVE_PER_SERVER,
        )
        if subscription_id is None:
            await _tetto_raggiunto(interaction, "Kick")
            return

        avviso = (
            ""
            if os.environ.get("KICK_CLIENT_ID") and os.environ.get("KICK_CLIENT_SECRET")
            else (
                "\n\n⚠️ Su questa istanza mancano KICK_CLIENT_ID e KICK_CLIENT_SECRET: "
                "l'avviso resta inattivo finché il proprietario del bot non li imposta."
            )
        )
        await interaction.response.send_message(
            f"✅ Sottoscrizione Kick creata (ID `KK-{subscription_id}`): notificherò in "
            f"{channel.mention} quando **{label}** va in diretta o termina.{avviso}",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "moduli",
        nome="opzioni",
        descrizione="Opzioni di un avviso: ruolo, fine diretta, bottone.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        id_avviso="ID dell'avviso, es. TW-2 o KK-1",
        ruolo="Ruolo da avvisare",
        fine="Messaggio a fine diretta",
        elimina="Cancella l'avviso a fine diretta",
        bottone="Bottone Guarda",
        annunci="Pubblica nei canali annunci",
        membro="Chi riceve il ruolo in diretta",
        pausa="Metti l'avviso in pausa (o riaccendilo) senza cancellarlo",
        parole="Parole del titolo, separate da virgola; «-parola» esclude; «-» da solo toglie il filtro",
        gioco="Solo questi giochi, separati da virgola (Twitch e Kick); «-» li ammette tutti",
        attesa="Minuti minimi tra due avvisi (0: nessuna pausa)",
        azzera="Torna alle opzioni di base",
    )
    async def opzioni(
        self,
        interaction: discord.Interaction,
        id_avviso: app_commands.Range[str, 1, 20],
        ruolo: discord.Role | None = None,
        fine: bool | None = None,
        elimina: bool | None = None,
        bottone: bool | None = None,
        annunci: bool | None = None,
        membro: discord.Member | None = None,
        pausa: bool | None = None,
        parole: app_commands.Range[str, 0, MAX_FILTRO] | None = None,
        gioco: app_commands.Range[str, 0, MAX_FILTRO] | None = None,
        attesa: app_commands.Range[int, 0, MAX_ATTESA_MINUTI] | None = None,
        azzera: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        letto = leggi_id_avviso(id_avviso)
        if letto is None:
            await interaction.response.send_message(
                "Formato ID non valido. Usa quello di /moduli alert elenco, es. RSS-3, TW-2, YT-1 o KK-4.",
                ephemeral=True,
            )
            return
        sigla, numero = letto
        subscription_id = id_avviso
        if not await self._esiste(sigla, numero, guild.id):
            await interaction.response.send_message(
                "Nessuna sottoscrizione trovata con questo ID in questo server.", ephemeral=True
            )
            return
        if azzera:
            await alert_options_repo.delete(sigla, numero, guild.id)
            await interaction.response.send_message("✅ Opzioni riportate ai valori di base.", ephemeral=True)
            return

        campi: dict = {}
        if ruolo is not None:
            errore = self._errore_ruolo_avviso(ruolo, guild)
            if errore:
                await interaction.response.send_message(errore, ephemeral=True)
                return
            campi["mention_role_id"] = ruolo.id
            # Il ruolo si avvisa solo se chi configura poteva pingarlo (D12).
            campi["ping_allowed"] = ruolo.mentionable or interaction.user.guild_permissions.mention_everyone
        if sigla in SIGLE_DIRETTA:
            if fine is not None:
                campi["notify_end"] = fine
            if elimina is not None:
                campi["delete_on_end"] = elimina
            if membro is not None:
                campi["live_member_id"] = membro.id
            if parole is not None:
                campi["title_words"] = "" if parole.strip() == "-" else parole.strip()
            if gioco is not None:
                campi["game_filter"] = "" if gioco.strip() == "-" else gioco.strip()
            if attesa is not None:
                campi["min_gap_minutes"] = attesa
        elif any(v is not None for v in (fine, elimina, membro, parole, gioco, attesa)):
            await interaction.response.send_message(
                "Fine diretta, ruolo «in diretta», filtri e pausa minima valgono solo per Twitch, YouTube e Kick.", ephemeral=True
            )
            return
        if pausa is not None:
            campi["paused"] = pausa
        if bottone is not None:
            campi["watch_button"] = bottone
        if annunci is not None:
            campi["crosspost"] = annunci
        if not campi:
            opz = await alert_options_repo.get(sigla, numero)
            await interaction.response.send_message(self._riepilogo(subscription_id, opz), ephemeral=True)
            return

        await alert_options_repo.set_fields(sigla, numero, guild.id, **campi)
        opz = await alert_options_repo.get(sigla, numero)
        extra = ""
        if campi.get("crosspost"):
            extra += "\nLa pubblicazione funziona solo se l'avviso va in un canale di annunci."
        if campi.get("live_member_id") and not await alert_options_repo.get_live_role(guild.id):
            extra += "\nImposta anche il ruolo con /moduli alert ruolo-live."
        await interaction.response.send_message(
            "✅ Opzioni aggiornate.\n" + self._riepilogo(subscription_id, opz) + extra, ephemeral=True
        )

    @staticmethod
    async def _esiste(sigla: str, numero: int, guild_id: int) -> bool:
        repo = {
            "RSS": feed_subscription_repo,
            "TW": twitch_subscription_repo,
            "YT": youtube_subscription_repo,
            "KK": kick_subscription_repo,
        }[sigla]
        return any(s.id == numero for s in await repo.list_subscriptions(guild_id))

    @staticmethod
    def _errore_ruolo_avviso(ruolo: discord.Role, guild: discord.Guild) -> str | None:
        if ruolo.is_default():
            return "Il ruolo @everyone non si può usare: gli avvisi non fanno mai @everyone."
        if ruolo.managed:
            return "Questo ruolo è gestito da un'integrazione e non si può usare."
        return None

    @staticmethod
    def _riepilogo(subscription_id: str, opz: AlertOptions) -> str:
        def sn(v: bool) -> str:
            return "sì" if v else "no"

        ruolo = f"<@&{opz.mention_role_id}>" if opz.mention_role_id else "nessuno"
        if opz.mention_role_id and not opz.ping_allowed:
            ruolo += " (non avvisato: il ruolo non è menzionabile)"
        membro = f"<@{opz.live_member_id}>" if opz.live_member_id else "nessuno"
        return (
            f"Opzioni di `{subscription_id.upper()}`:\n"
            f"• Ruolo da avvisare: {ruolo}\n"
            f"• Messaggio di fine diretta: {sn(opz.notify_end)}\n"
            f"• Cancella l'avviso a fine diretta: {sn(opz.delete_on_end)}\n"
            f"• Bottone «Guarda»: {sn(opz.watch_button)}\n"
            f"• Pubblica nei canali annunci: {sn(opz.crosspost)}\n"
            f"• Membro per il ruolo «in diretta»: {membro}\n"
            f"• In pausa: {sn(opz.paused)}\n"
            f"• Parole del titolo: {opz.title_words or 'nessun filtro'}\n"
            f"• Giochi: {opz.game_filter or 'tutti'}\n"
            f"• Pausa minima tra due avvisi: {opz.min_gap_minutes} min"
        )

    @comando_di_gruppo(
        "moduli",
        nome="ruolo-live",
        descrizione="Ruolo dato a chi è in diretta.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(ruolo="Il ruolo (vuoto: mostra quello attuale)")
    async def ruolo_live(self, interaction: discord.Interaction, ruolo: discord.Role | None = None) -> None:
        guild = interaction.guild
        if guild is None:
            return
        if ruolo is None:
            attuale = await alert_options_repo.get_live_role(guild.id)
            await interaction.response.send_message(
                f"Ruolo «in diretta»: <@&{attuale}>." if attuale else "Nessun ruolo «in diretta» impostato.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        if ruolo.is_default() or ruolo.managed:
            await interaction.response.send_message(
                "Questo ruolo non si può usare: serve un ruolo normale, non @everyone né di un'integrazione.",
                ephemeral=True,
            )
            return
        proprietario = interaction.user.id == guild.owner_id
        if not proprietario and ruolo >= interaction.user.top_role:
            await interaction.response.send_message(
                "Non puoi scegliere un ruolo uguale o superiore al tuo.", ephemeral=True
            )
            return
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles or ruolo >= me.top_role:
            await interaction.response.send_message(
                "Non riesco a dare questo ruolo: mi serve il permesso «Gestire i ruoli» "
                "e il mio ruolo più alto deve stare sopra quello scelto.",
                ephemeral=True,
            )
            return
        await alert_options_repo.set_live_role(guild.id, ruolo.id)
        await interaction.response.send_message(
            f"✅ Ruolo «in diretta» impostato su {ruolo.mention}. Lo riceve chi è collegato a un avviso "
            "Twitch, YouTube o Kick con `/moduli alert opzioni` (campo `membro`) e lo perde a fine diretta.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "moduli",
        nome="guida-social",
        descrizione="Avvisi per TikTok, Instagram e X.",
        sottogruppo=SOTTOGRUPPO,
    )
    async def guida_social(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=discord.Embed(title="Avvisi da TikTok, Instagram e X", description=GUIDA_SOCIAL,
                                color=discord.Color.blurple()),
            ephemeral=True,
        )

    @comando_di_gruppo(
        "moduli",
        nome="elenco",
        descrizione="Elenca gli avvisi del server.",
        sottogruppo=SOTTOGRUPPO,
    )
    async def list_alerts(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        feed_subs = await feed_subscription_repo.list_subscriptions(guild.id)
        twitch_subs = await twitch_subscription_repo.list_subscriptions(guild.id)
        youtube_subs = await youtube_subscription_repo.list_subscriptions(guild.id)
        kick_subs = await kick_subscription_repo.list_subscriptions(guild.id)
        webhooks = await custom_webhook_repo.list_webhooks(guild.id)

        if not (feed_subs or twitch_subs or youtube_subs or kick_subs or webhooks):
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
            f"`KK-{s.id}` **{s.label}** (Kick: {s.kick_slug}) → <#{s.channel_id}>"
            f"{' 🔴 in diretta' if s.last_known_live else ''}"
            for s in kick_subs
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
            description=_elenco_tagliato(righe),
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
