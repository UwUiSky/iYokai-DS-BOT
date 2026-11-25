"""
cogs/utility/greetings.py
============================
Messaggi di benvenuto, addio, boost e ban (martello più addio, D37). Modulo gratuito.
Funzioni coperte: SPEC §14.4-14.6
Dipende da: core/greetings_logic.py, core/greetings_uscite_logic.py
"""

# L'immagine di benvenuto (NF-11) si disegna in core/welcome_image.py.

from __future__ import annotations

import io
import logging
from datetime import datetime
import time

import discord
from discord import app_commands
from discord.ext import commands

from core import channel_router as router
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.admin_mentions_logic import (
    menzioni_ammesse,
    taglia_messaggio,
    utente_puo_pingare_ruoli,
)
from core.leveling_logic import colore_valido
from core.role_menu_logic import valida_emoji
from core.greetings_logic import (
    PrimiMessaggi,
    DEFAULT_BOOST_TEMPLATE,
    DEFAULT_GOODBYE_TEMPLATE,
    DEFAULT_WELCOME_TEMPLATE,
    MAX_MESSAGE_LENGTH,
    analizza_reazioni,
    analizza_varianti,
    lunghezza_dopo_segnaposto,
    usa_segnaposto_inviti,
    render_template,
    scegli_testo,
)
from core import greetings_uscite_logic as uscite
from core import invite_service
from core.i18n import lingua_risposta, t, testo_per
from core.greetings_embed_logic import DOVE, TOGLI, embed_con_segnaposto
from core.topic_avviso_logic import PAUSA_PER_CANALE_SECONDI, messaggio_avviso, va_annunciato
from core.ui_base import BaseModal, BaseView
from core.premium import PremiumModule, registry
from core.repositories.greetings_repo import greetings_repo
from core.repositories.ruoli_extra_repo import RuoliExtraRepository
from core.ruoli_extra_logic import scegli_immagine
from core.repositories.saved_embed_repo import saved_embed_repo
from core.embed_builder_logic import MAX_NOME as MAX_NOME_EMBED
from core.safe_image import ImmagineTroppoGrande, SandboxNonDisponibile, run_image_task
from core.security_raid_state import raid_in_corso
from core.welcome_image import (
    ALLINEAMENTI,
    MAX_TESTO,
    FORME,
    MAX_SFONDO_BYTE,
    MAX_TITOLO,
    MISURA_MAX,
    MISURA_MIN,
    MODELLI,
    DatiBenvenuto,
    prepara_sfondo,
    render_welcome_image,
)

logger = logging.getLogger("iyokai.greetings")

MODULE_GREETINGS = "greetings"


def _render_for_member(template: str, member: discord.Member, inviti: dict | None = None) -> str:
    return render_template(
        template,
        user_mention=member.mention,
        username=discord.utils.escape_mentions(member.name),
        server_name=discord.utils.escape_mentions(member.guild.name),
        member_count=member.guild.member_count or 0,
        user_id=member.id,
        display_name=discord.utils.escape_mentions(member.display_name),
        server_id=member.guild.id,
        creato_il=int(member.created_at.timestamp()),
        eta_giorni=(
            max((discord.utils.utcnow() - member.created_at).days, 0)
            if isinstance(member.created_at, datetime) else None
        ),
        ruoli_ids=frozenset(r.id for r in member.roles),
        **(inviti or {}),
    )


async def _embed_salvato(member: discord.Member, nome: str, inviti: dict | None = None) -> discord.Embed | None:
    """RUO-001, 014, 015: l'embed salvato con i segnaposto del membro; None se non c'è o non è valido."""
    if not nome:
        return None
    salvato = await saved_embed_repo.get(member.guild.id, nome)
    if salvato is None:
        return None
    return embed_con_segnaposto(salvato.data, lambda testo: _render_for_member(testo, member, inviti))


async def _metti_reazioni(messaggio: discord.Message, reazioni: list[str]) -> None:
    """RUO-023/025: le reazioni scelte dall'admin sul benvenuto. Una che fallisce non ferma le altre."""
    for emoji in reazioni:
        try:
            await messaggio.add_reaction(emoji)
        except discord.HTTPException:
            logger.info("Reazione %s non messa sul benvenuto.", emoji[:40])


class ExtraBenvenutoModal(BaseModal, title="Benvenuto: DM, varianti, reazioni"):
    """RUO-013, 017, 023, 025: tre campi, tutti facoltativi (vuoto = spento)."""

    dm = discord.ui.TextInput(
        label="Testo del DM (vuoto = come nel canale)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=MAX_MESSAGE_LENGTH,
    )
    varianti = discord.ui.TextInput(
        label="Altre versioni del testo, una per riga",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000,
    )
    reazioni = discord.ui.TextInput(
        label="Reazioni sul benvenuto (max 5, con spazi)",
        required=False,
        max_length=120,
    )
    ban = discord.ui.TextInput(
        label="Messaggio per i ban (vuoto = quello di base)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=MAX_MESSAGE_LENGTH,
    )
    primo = discord.ui.TextInput(
        label="Emoji sul primo messaggio (vuoto = no)",
        required=False,
        max_length=60,
    )

    def __init__(self, config) -> None:
        super().__init__()
        self.dm.default = config.welcome_dm_message or None
        self.varianti.default = "\n".join(config.welcome_variants)[:4000] or None
        self.reazioni.default = " ".join(config.welcome_reactions) or None
        self.ban.default = config.ban_message or None
        self.primo.default = config.first_message_reaction or None

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        dm = (self.dm.value or "").strip()
        varianti, errore = analizza_varianti(self.varianti.value or "")
        reazioni = []
        if errore is None:
            reazioni, errore = analizza_reazioni(self.reazioni.value or "")
        ban = (self.ban.value or "").strip()
        primo = (self.primo.value or "").strip()
        if errore is None and primo and not valida_emoji(primo):  # RUO-024
            errore = f"«{primo[:30]}» non è un'emoji."
        for testo in ([dm] if dm else []) + varianti + ([ban] if ban else []):
            if errore is None and "<@&" in testo and not utente_puo_pingare_ruoli(interaction.user):
                errore = "Per citare un ruolo serve il permesso «Menziona tutti»."
            if errore is None:
                errore = _errore_lunghezza(guild, testo)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await greetings_repo.set_welcome_extra(guild.id, dm, varianti, reazioni, ban)
        await greetings_repo.set_first_reaction(guild.id, primo)
        await interaction.response.send_message(
            await testo_per(interaction, "greetings_salvato_dm_varianti_reazioni_ban", v1=(await testo_per(interaction, "greetings_con_testo_suo")) if dm else (await testo_per(interaction, "greetings_come_il_canale")), v2=len(varianti), v3=len(reazioni), v4=(await testo_per(interaction, "greetings_con_testo_suo")) if ban else (await testo_per(interaction, "greetings_con_il_testo_di_base"))),
            ephemeral=True,
        )


async def _modello(salvato: str, predefinito: str, chiave: str, guild_id: int) -> str:
    """Il testo salvato dall'admin com'è; se è ancora quello di base, quello della lingua del server (NF-06)."""
    return t(chiave, await lingua_risposta(guild_id, None, pubblica=True)) if salvato == predefinito else salvato


async def _invia_con_grafica(
    channel, testo, grafica, menzioni, guild_id: int, nome: str, embed_salvato: discord.Embed | None = None
) -> None:
    """D37: testo più grafica (link https o file), con l'embed salvato se c'è (RUO-015). Se la grafica non passa, il testo parte lo stesso."""
    url, immagine, nome_file = grafica if grafica else (None, None, None)
    extra = {"embed": embed_salvato} if embed_salvato is not None else {}
    try:
        try:
            if url:
                embed = discord.Embed()
                embed.set_image(url=url)
                if embed_salvato is None:
                    await channel.send(testo, embed=embed, allowed_mentions=menzioni)
                else:
                    await channel.send(testo, embeds=[embed, embed_salvato], allowed_mentions=menzioni)
            elif immagine:
                file = discord.File(io.BytesIO(immagine), filename=nome_file or "grafica.png")
                await channel.send(testo, file=file, allowed_mentions=menzioni, **extra)
            else:
                await channel.send(testo, allowed_mentions=menzioni, **extra)
        except discord.HTTPException:
            if not url and not immagine:
                raise
            await channel.send(testo, allowed_mentions=menzioni)
    except discord.HTTPException:
        logger.warning("Impossibile inviare il messaggio %s nel server %s.", nome, guild_id)


class UsciteModal(BaseModal, title="Ban e addio: cosa esce e la grafica"):
    """D37: quali messaggi escono e la grafica (file o link https) di ciascuno. Campo vuoto = non cambiare."""

    def __init__(self, config) -> None:
        super().__init__()
        self.modo = discord.ui.Select(
            options=[
                discord.SelectOption(label=etichetta, value=valore, default=valore == config.leave_mode)
                for valore, etichetta in uscite.ETICHETTE_MODO.items()
            ],
            required=True,
        )
        self.file_ban = discord.ui.FileUpload(required=False, min_values=0, max_values=1)
        self.link_ban = discord.ui.TextInput(required=False, max_length=uscite.MAX_LINK, placeholder="https://… oppure «togli»")
        self.file_addio = discord.ui.FileUpload(required=False, min_values=0, max_values=1)
        self.link_addio = discord.ui.TextInput(required=False, max_length=uscite.MAX_LINK, placeholder="https://… oppure «togli»")
        self.add_item(discord.ui.Label(text="Quali messaggi escono", component=self.modo))
        self.add_item(discord.ui.Label(text="Grafica ban: file (PNG, JPEG, GIF, WebP)", component=self.file_ban))
        self.add_item(discord.ui.Label(text="Grafica ban: oppure link https", component=self.link_ban))
        self.add_item(discord.ui.Label(text="Grafica addio: file (PNG, JPEG, GIF, WebP)", component=self.file_addio))
        self.add_item(discord.ui.Label(text="Grafica addio: oppure link https", component=self.link_addio))

    async def _grafica(self, tipo, caricati, link: str):
        """(scrittura da fare, errore): scrittura = ('file', byte, nome) | ('link', url) | ('togli',) | None."""
        if caricati:
            allegato = caricati[0]
            if allegato.size > uscite.MAX_BYTE_GRAFICA:
                return None, f"Grafica del {tipo}: il file pesa troppo (limite 3 MB)."
            dati = await allegato.read()
            estensione, errore = await run_image_task(uscite.valida_file, dati)
            if errore:
                return None, f"Grafica del {tipo}: {errore}"
            return ("file", dati, f"{tipo}.{estensione}"), None
        link = link.strip()
        if not link:
            return None, None
        if link.lower() == uscite.TOGLI:
            return ("togli",), None
        errore = await uscite.valida_link(link)
        return (("link", link), None) if errore is None else (None, f"Grafica del {tipo}: {errore}")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        modo = self.modo.values[0] if self.modo.values else ""
        if not uscite.modo_valido(modo):
            await interaction.response.send_message(await testo_per(interaction, "modmail_scelta_non_valida"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)  # file e link si controllano: può servire qualche secondo
        azioni = {}
        for tipo, caricati, link in (
            (uscite.TIPO_BAN, self.file_ban.values, self.link_ban.value or ""),
            (uscite.TIPO_ADDIO, self.file_addio.values, self.link_addio.value or ""),
        ):
            azione, errore = await self._grafica(tipo, caricati, link)
            if errore:
                await interaction.followup.send(errore, ephemeral=True)
                return
            azioni[tipo] = azione
        await greetings_repo.set_leave_mode(guild.id, modo)
        for tipo, azione in azioni.items():
            if azione is None:
                continue
            if azione[0] == "file":
                await greetings_repo.set_grafica(guild.id, tipo, image=azione[1], filename=azione[2])
            elif azione[0] == "link":
                await greetings_repo.set_grafica(guild.id, tipo, url=azione[1])
            else:
                await greetings_repo.clear_grafica(guild.id, tipo)
        config = await greetings_repo.get_config(guild.id)
        avviso = ""
        if modo != uscite.MODO_NESSUNO and (not config.goodbye_enabled or config.goodbye_channel_id is None):
            avviso = " Il canale dell'addio però non è attivo: configuralo con `/admin-benvenuto addio`."
        await interaction.followup.send(f"Salvato: escono {uscite.ETICHETTE_MODO[modo]}.{avviso}", ephemeral=True)


class ExtraBenvenutoView(BaseView):
    """`/admin-benvenuto extra`: due finestre, i testi del benvenuto e quella di ban e addio (D37)."""

    def __init__(self, config) -> None:
        super().__init__(timeout=300)
        self._config = config

    @discord.ui.button(label="Testi e reazioni", style=discord.ButtonStyle.primary)
    async def testi(self, interaction: discord.Interaction, _bottone: discord.ui.Button) -> None:
        await interaction.response.send_modal(ExtraBenvenutoModal(self._config))

    @discord.ui.button(label="Ban e addio", style=discord.ButtonStyle.secondary)
    async def ban_addio(self, interaction: discord.Interaction, _bottone: discord.ui.Button) -> None:
        await interaction.response.send_modal(UsciteModal(self._config))


def _testo_sull_immagine(modello: str, member: discord.Member) -> str:
    """RUO-008: il testo libero con i segnaposto; sull'immagine `{user}` è il nome, non una menzione."""
    if not modello:
        return ""
    return render_template(
        modello,
        user_mention=member.display_name,
        username=member.name,
        server_name=member.guild.name,
        member_count=member.guild.member_count or 0,
        user_id=member.id,
        display_name=member.display_name,
        server_id=member.guild.id,
    )


async def _immagine_a_caso(guild_id: int) -> bytes | None:
    """RUO-012: una delle immagini proprie del server, a caso; None se non ce ne sono. Un errore non ferma il benvenuto."""
    try:
        repo = RuoliExtraRepository(greetings_repo.pool_provider())
        scelta = scegli_immagine(await repo.id_immagini_benvenuto(guild_id))
        return await repo.immagine_benvenuto(guild_id, scelta) if scelta is not None else None
    except Exception:
        logger.exception("Immagini proprie del benvenuto non lette nel server %s.", guild_id)
        return None


async def _file_benvenuto(config, member: discord.Member) -> discord.File | None:
    """
    NF-11: l'immagine di benvenuto, o None se spenta o non disegnabile (il testo parte lo stesso).
    RUO-012: se il server ha immagini proprie, una a caso fa da sfondo del biglietto; con il biglietto spento
    viene allegata così com'è (già ricodificata al salvataggio).
    """
    propria = await _immagine_a_caso(member.guild.id)
    if not config.welcome_image_enabled:
        return discord.File(io.BytesIO(propria), filename="benvenuto.jpg") if propria is not None else None
    try:
        try:
            avatar = await member.display_avatar.replace(size=256, format="png").read()
        except (discord.HTTPException, AttributeError):
            avatar = None
        sfondo = propria if propria is not None else (
            await greetings_repo.get_welcome_background(member.guild.id)
            if config.welcome_image_has_background
            else None
        )
        dati = DatiBenvenuto(
            nome=member.display_name,
            numero=member.guild.member_count or 0,
            titolo=config.welcome_image_title,
            modello=config.welcome_image_template,
            forma=config.welcome_image_shape,
            colore_testo=config.welcome_image_color,
            opacita=config.welcome_image_opacity,
            testo=_testo_sull_immagine(config.welcome_image_text, member),
            allineamento=config.welcome_image_align,
            colore_nome=config.welcome_image_name_color,
            larghezza=config.welcome_image_width,
            altezza=config.welcome_image_height,
            trasparente=config.welcome_image_transparent,
        )
        png = await run_image_task(render_welcome_image, dati, avatar, sfondo)
    except (SandboxNonDisponibile, Exception):
        logger.exception("Immagine di benvenuto non disegnata nel server %s.", member.guild.id)
        return None
    return discord.File(io.BytesIO(png), filename="benvenuto.png")


# L'opzione accetta il testo grezzo: il limite vero (2000) si controlla
# dopo i segnaposto, a configurazione, con `_errore_lunghezza`.
TestoMessaggio = app_commands.Range[str, 1, MAX_MESSAGE_LENGTH]


def _errore_lunghezza(guild: discord.Guild, template: str) -> str | None:
    """M 10.2 (LIM-10): None se il testo, a segnaposto espansi, sta in 2000 caratteri."""
    lunghezza = lunghezza_dopo_segnaposto(template, guild.name, guild.member_count or 0)
    if lunghezza <= MAX_MESSAGE_LENGTH:
        return None
    return (
        f"Con i segnaposto sostituiti il messaggio arriva a {lunghezza} caratteri: "
        f"Discord ne accetta {MAX_MESSAGE_LENGTH}. Accorcialo."
    )


def _ping_ruoli(interaction: discord.Interaction, message: str | None, precedente: bool) -> bool:
    """
    D12: il permesso di chi configura conta solo se sta scrivendo il testo.
    Chi cambia soltanto canale o stato (es. un moderatore con solo "Gestisci
    server") non accende né spegne il ping deciso da chi ha scritto il testo.
    """
    return utente_puo_pingare_ruoli(interaction.user) if message is not None else precedente


_SG_BENVENUTO = ("benvenuto", "Messaggi di benvenuto, addio e boost")


@autocomplete_protetto(Livello.ADMIN)
async def _completa_embed(interaction: discord.Interaction, current: str):
    """Fino a 25 nomi di embed salvati che iniziano o contengono il testo scritto."""
    if interaction.guild is None:
        return []
    parola = current.lower().strip()
    nomi = [e.name for e in await saved_embed_repo.list(interaction.guild.id) if parola in e.name]
    return [app_commands.Choice(name=n, value=n) for n in nomi[:25]]


class GreetingsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._primi = PrimiMessaggi()  # RUO-024
        self._ultimi_topic: dict[int, float] = {}  # RUO-027: canale -> ultimo avviso

    # ================================================================
    # Eventi
    # ================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # Niente benvenuto ai bot: non possono ricevere messaggi privati
        # da un altro bot e li ha aggiunti un amministratore.
        if member.bot:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_GREETINGS):
            return

        config = await greetings_repo.get_config(member.guild.id)
        if not config.welcome_enabled:
            return

        modello = scegli_testo(await _modello(config.welcome_message, DEFAULT_WELCOME_TEMPLATE, "greet_base_welcome", member.guild.id), config.welcome_variants)
        inviti = None
        if usa_segnaposto_inviti(modello, config.welcome_dm_message):
            inviti = await invite_service.dati_per_benvenuto(member.guild, member)
        testo = taglia_messaggio(_render_for_member(modello, member, inviti))
        testo_dm = (
            taglia_messaggio(_render_for_member(config.welcome_dm_message, member, inviti))
            if config.welcome_dm_message
            else testo
        )
        if config.first_message_reaction:  # RUO-024
            self._primi.registra(member.guild.id, member.id, time.monotonic())
        menzioni = menzioni_ammesse(config.welcome_ping_ruoli)
        embed = await _embed_salvato(member, config.welcome_embed, inviti)
        extra = {"embed": embed} if embed is not None else {}  # RUO-001

        if config.welcome_channel_id is not None:
            channel = member.guild.get_channel(config.welcome_channel_id)
            if isinstance(channel, discord.ForumChannel):
                # Router (§18.1): un forum riceve i benvenuti in un solo post, senza immagine né reazioni.
                dest = await router.destinazione(member.guild, router.TIPO_BENVENUTO, channel.id)
                if dest is not None:
                    await router.invia_a(dest, member.guild, router.TIPO_BENVENUTO, content=testo, allowed_mentions=menzioni)
            elif channel is None:
                await router.avvisa_proprietario(
                    member.guild, router.TIPO_BENVENUTO, config.welcome_channel_id, "il canale non esiste più"
                )
            elif isinstance(channel, discord.TextChannel):
                # Durante un raid solo testo: disegnare un'immagine per ogni ingresso è lavoro sprecato.
                puo_allegare = channel.permissions_for(member.guild.me).attach_files
                allegato = (
                    None
                    if raid_in_corso(member.guild.id) or not puo_allegare
                    else await _file_benvenuto(config, member)
                )
                try:
                    try:
                        if allegato is not None and config.welcome_image_order == "solo_immagine":
                            inviato = await channel.send(file=allegato, allowed_mentions=menzioni)  # RUO-010
                        elif allegato is not None and config.welcome_image_order == "immagine_prima":
                            await channel.send(file=allegato, allowed_mentions=menzioni)
                            allegato = None  # già uscita: se il testo fallisce non si rimanda
                            inviato = await channel.send(testo, allowed_mentions=menzioni, **extra)
                        elif allegato is not None:
                            inviato = await channel.send(testo, file=allegato, allowed_mentions=menzioni, **extra)
                        else:
                            inviato = await channel.send(testo, allowed_mentions=menzioni, **extra)
                    except discord.HTTPException:
                        if allegato is None and not extra:
                            raise
                        # Immagine o embed non passati (permessi cambiati, rifiuto): il testo parte lo stesso.
                        allegato = None
                        extra = {}
                        inviato = await channel.send(testo, allowed_mentions=menzioni)
                    if not raid_in_corso(member.guild.id):  # durante un raid: niente chiamate in più
                        await _metti_reazioni(inviato, config.welcome_reactions)
                except discord.HTTPException:
                    logger.warning(
                        "Impossibile inviare il welcome message nel server %s.",
                        member.guild.id,
                    )

        # M 10.16: durante un raid niente DM di benvenuto (non si scrive agli
        # account entrati nel raid).
        if config.welcome_dm and not raid_in_corso(member.guild.id):
            try:
                embed_dm = await _embed_salvato(member, config.dm_embed, inviti)  # RUO-014
                await member.send(
                    testo_dm, allowed_mentions=menzioni_ammesse(False), **({"embed": embed_dm} if embed_dm else {})
                )
            except discord.HTTPException:
                pass  # DM chiusi: non è un errore da segnalare, è normale

    @commands.Cog.listener()
    async def on_guild_channel_update(self, prima: discord.abc.GuildChannel, dopo: discord.abc.GuildChannel) -> None:
        """RUO-027: avviso quando cambia l'argomento di un canale di testo che tutti possono vedere."""
        if not isinstance(dopo, discord.TextChannel) or not va_annunciato(getattr(prima, "topic", None), dopo.topic):
            return
        guild = dopo.guild
        if not await db.is_module_active_for_guild(guild.id, MODULE_GREETINGS):
            return
        config = await greetings_repo.get_config(guild.id)
        if config.topic_notice_channel_id is None or config.topic_notice_channel_id == dopo.id:
            return
        if not dopo.permissions_for(guild.default_role).view_channel:
            return  # un canale privato non rivela il suo argomento in uno pubblico
        ora = time.monotonic()
        if ora - self._ultimi_topic.get(dopo.id, -1e9) < PAUSA_PER_CANALE_SECONDI:
            return
        canale = guild.get_channel(config.topic_notice_channel_id)
        if not isinstance(canale, discord.TextChannel):
            return
        if len(self._ultimi_topic) > 2000:
            self._ultimi_topic.clear()
        self._ultimi_topic[dopo.id] = ora
        try:
            await canale.send(
                messaggio_avviso(dopo.mention, getattr(prima, "topic", None), dopo.topic),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            logger.info("Avviso sull'argomento non inviato nel server %s.", guild.id)

    @commands.Cog.listener()
    async def on_message(self, messaggio: discord.Message) -> None:
        """RUO-024: l'emoji sul primo messaggio di chi è appena entrato. Non si legge il testo, solo chi scrive."""
        if messaggio.guild is None or messaggio.author.bot or len(self._primi) == 0:
            return
        if messaggio.type not in (discord.MessageType.default, discord.MessageType.reply):
            return
        if not self._primi.consuma(messaggio.guild.id, messaggio.author.id, time.monotonic()):
            return
        config = await greetings_repo.get_config(messaggio.guild.id)
        if not config.first_message_reaction:
            return
        try:
            await messaggio.add_reaction(config.first_message_reaction)
        except discord.HTTPException:
            logger.info("Reazione sul primo messaggio non messa nel server %s.", messaggio.guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_GREETINGS):
            return

        config = await greetings_repo.get_config(member.guild.id)
        manda = config.goodbye_enabled and config.goodbye_channel_id is not None and uscite.invia_addio(config.leave_mode)
        # D37: se l'uscita è un ban, prima il martello e poi l'addio; durante un raid niente addio ai bannati.
        # Si consuma sempre lo stato del ban, anche quando l'addio è spento.
        attendi = manda and (config.leave_mode == uscite.MODO_ENTRAMBI or raid_in_corso(member.guild.id))
        if await uscite.addio_soppresso(member.guild.id, member.id, attendi=attendi) or not manda:
            return
        channel = member.guild.get_channel(config.goodbye_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        testo = taglia_messaggio(_render_for_member(await _modello(config.goodbye_message, DEFAULT_GOODBYE_TEMPLATE, "greet_base_goodbye", member.guild.id), member))
        await _invia_con_grafica(
            channel, testo, await greetings_repo.get_grafica(member.guild.id, uscite.TIPO_ADDIO),
            menzioni_ammesse(config.goodbye_ping_ruoli), member.guild.id, "goodbye",
            await _embed_salvato(member, config.goodbye_embed),
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """RUO-016, D37: il «martello» nel canale dell'addio (di base, con testo nostro; il server può cambiarlo o spegnerlo)."""
        if user.bot:
            return
        if not await db.is_module_active_for_guild(guild.id, MODULE_GREETINGS):
            return
        config = await greetings_repo.get_config(guild.id)
        # Durante un raid: niente martello (i ban in massa non riempiono il canale) e niente addio per lui.
        # L'addio aspetta il segnale, dato solo DOPO l'invio del martello: così esce sempre secondo.
        in_raid = raid_in_corso(guild.id)
        try:
            await self._martello(guild, user, config, in_raid)
        finally:
            uscite.segna_ban(guild.id, user.id, soppresso=in_raid)

    async def _martello(self, guild: discord.Guild, user: discord.User, config, in_raid: bool) -> None:
        if not uscite.invia_ban(config.leave_mode) or not config.goodbye_enabled or config.goodbye_channel_id is None:
            return
        if in_raid:
            return
        channel = guild.get_channel(config.goodbye_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        testo = render_template(
            uscite.testo_ban(config.ban_message),
            user_mention=user.mention,
            username=discord.utils.escape_mentions(user.name),
            server_name=discord.utils.escape_mentions(guild.name),
            member_count=guild.member_count or 0,
            user_id=user.id,
            display_name=discord.utils.escape_mentions(user.display_name),
            server_id=guild.id,
        )
        await _invia_con_grafica(
            channel, taglia_messaggio(testo), await greetings_repo.get_grafica(guild.id, uscite.TIPO_BAN),
            menzioni_ammesse(config.goodbye_ping_ruoli), guild.id, "ban",
        )

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        # Rilevamento inizio boost: premium_since passa da None a un
        # timestamp. Non ci interessa il caso opposto (fine boost) né
        # i cambi di ruolo/nickname — quelli sono gestiti da
        # cogs/logging/basic_logs.py, un evento diverso con uno scopo
        # diverso (log, non annuncio).
        if before.premium_since is not None or after.premium_since is None:
            return

        if not await db.is_module_active_for_guild(after.guild.id, MODULE_GREETINGS):
            return

        config = await greetings_repo.get_config(after.guild.id)
        if not config.boost_enabled or config.boost_channel_id is None:
            return

        channel = after.guild.get_channel(config.boost_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        testo = taglia_messaggio(_render_for_member(await _modello(config.boost_message, DEFAULT_BOOST_TEMPLATE, "greet_base_boost", after.guild.id), after))
        try:
            await channel.send(
                testo, allowed_mentions=menzioni_ammesse(config.boost_ping_ruoli)
            )
        except discord.HTTPException:
            logger.warning(
                "Impossibile inviare il boost message nel server %s.", after.guild.id
            )

    # ================================================================
    # Comandi
    # ================================================================

    @comando_di_gruppo(
        "admin-benvenuto",
        nome="messaggio",
        descrizione="Configura il messaggio di benvenuto.",
    )
    @app_commands.describe(
        enabled="Attiva o disattiva il welcome message",
        channel="Canale dove pubblicarlo",
        message="Testo del messaggio ({user}, {username}, {server}, {membercount})",
        dm="Manda anche un DM all'utente (se non lo indichi resta com'è)",
    )
    async def welcome_setup(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | discord.ForumChannel | None = None,
        message: TestoMessaggio | None = None,
        dm: bool | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return

        config_attuale = await greetings_repo.get_config(guild.id)
        canale_finale = channel or (
            guild.get_channel(config_attuale.welcome_channel_id)
            if config_attuale.welcome_channel_id
            else None
        )
        if enabled and canale_finale is None:
            await interaction.response.send_message(
                await testo_per(interaction, "greetings_specifica_un_canale_per_attivare"), ephemeral=True
            )
            return

        testo_finale = message or config_attuale.welcome_message
        errore = _errore_lunghezza(guild, testo_finale)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        await greetings_repo.set_welcome(
            guild.id,
            enabled=enabled,
            channel_id=canale_finale.id if canale_finale else 0,
            message=testo_finale,
            dm=config_attuale.welcome_dm if dm is None else dm,
            ping_ruoli=_ping_ruoli(interaction, message, config_attuale.welcome_ping_ruoli),
        )
        await interaction.response.send_message(
            await testo_per(interaction, "greetings_welcome_message", v1=(await testo_per(interaction, "greetings_attivato")) if enabled else (await testo_per(interaction, "greetings_disattivato"))), ephemeral=True
        )

    @comando_di_gruppo(
        "admin-benvenuto",
        nome="extra",
        descrizione="Benvenuto: DM, varianti, reazioni; messaggi di ban e addio.",
    )
    async def welcome_extra(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return
        config = await greetings_repo.get_config(interaction.guild.id)
        await interaction.response.send_message(
            await testo_per(interaction, "greetings_cosa_vuoi_cambiare_il_testo"),
            view=ExtraBenvenutoView(config), ephemeral=True,
        )

    @comando_di_gruppo(
        "admin-benvenuto",
        nome="addio",
        descrizione="Configura il messaggio di addio.",
    )
    @app_commands.describe(
        enabled="Attiva o disattiva il goodbye message",
        channel="Canale dove pubblicarlo",
        message="Testo del messaggio ({username}, {server}, {membercount})",
    )
    async def goodbye_setup(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | None = None,
        message: TestoMessaggio | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return

        config_attuale = await greetings_repo.get_config(guild.id)
        canale_finale = channel or (
            guild.get_channel(config_attuale.goodbye_channel_id)
            if config_attuale.goodbye_channel_id
            else None
        )
        if enabled and canale_finale is None:
            await interaction.response.send_message(
                await testo_per(interaction, "greetings_specifica_un_canale_per_attivare_2"), ephemeral=True
            )
            return

        testo_finale = message or config_attuale.goodbye_message
        errore = _errore_lunghezza(guild, testo_finale)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        await greetings_repo.set_goodbye(
            guild.id,
            enabled=enabled,
            channel_id=canale_finale.id if canale_finale else 0,
            message=testo_finale,
            ping_ruoli=_ping_ruoli(interaction, message, config_attuale.goodbye_ping_ruoli),
        )
        await interaction.response.send_message(
            await testo_per(interaction, "greetings_goodbye_message", v1=(await testo_per(interaction, "greetings_attivato")) if enabled else (await testo_per(interaction, "greetings_disattivato"))), ephemeral=True
        )

    @comando_di_gruppo(
        "admin-benvenuto",
        nome="boost",
        descrizione="Configura il messaggio di boost.",
    )
    @app_commands.describe(
        enabled="Attiva o disattiva il boost message",
        channel="Canale dove pubblicarlo",
        message="Testo del messaggio ({user}, {server})",
    )
    async def boost_setup(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | None = None,
        message: TestoMessaggio | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return

        config_attuale = await greetings_repo.get_config(guild.id)
        canale_finale = channel or (
            guild.get_channel(config_attuale.boost_channel_id)
            if config_attuale.boost_channel_id
            else None
        )
        if enabled and canale_finale is None:
            await interaction.response.send_message(
                await testo_per(interaction, "greetings_specifica_un_canale_per_attivare_3"), ephemeral=True
            )
            return

        testo_finale = message or config_attuale.boost_message
        errore = _errore_lunghezza(guild, testo_finale)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        await greetings_repo.set_boost(
            guild.id,
            enabled=enabled,
            channel_id=canale_finale.id if canale_finale else 0,
            message=testo_finale,
            ping_ruoli=_ping_ruoli(interaction, message, config_attuale.boost_ping_ruoli),
        )
        await interaction.response.send_message(
            await testo_per(interaction, "greetings_boost_message", v1=(await testo_per(interaction, "greetings_attivato")) if enabled else (await testo_per(interaction, "greetings_disattivato"))), ephemeral=True
        )

    @comando_di_gruppo(
        "admin-benvenuto",
        nome="immagine",
        descrizione="Aggiungi al benvenuto un'immagine con avatar, nome e numero del membro.",
    )
    @app_commands.describe(
        attiva="Attiva o disattiva l'immagine",
        modello="Il modello pronto da usare",
        sfondo="Uno sfondo tuo (immagine sotto 3 MB); sostituisce il modello",
        forma_avatar="Avatar tondo o quadrato",
        colore_testo="Colore del testo, per esempio #FFFFFF",
        titolo="La scritta in alto (massimo 40 caratteri)",
        togli_sfondo="Torna al modello pronto cancellando lo sfondo caricato",
        opacita="Quanto si vede lo sfondo caricato, da 0 a 100 (di base 65)",
        testo="Riga di testo sull'immagine, con i segnaposto (massimo 100; «togli» la toglie)",
        ordine="Se l'immagine va con il testo, prima del testo o da sola",
        allineamento="Dove stanno i testi accanto all'avatar",
        colore_nome="Colore del nome, per esempio #FFD700 (oppure «predefinito»)",
        trasparente="Sì = nessuno sfondo: solo avatar e testi (il PNG resta trasparente)",
        larghezza="Larghezza in pixel, da 64 a 2048 (di base 1024)",
        altezza="Altezza in pixel, da 64 a 2048 (di base 400)",
    )
    @app_commands.choices(
        modello=[app_commands.Choice(name=nome, value=nome) for nome in MODELLI],
        forma_avatar=[app_commands.Choice(name=forma, value=forma) for forma in FORME],
        ordine=[
            app_commands.Choice(name="insieme al testo", value="insieme"),
            app_commands.Choice(name="immagine prima del testo", value="immagine_prima"),
            app_commands.Choice(name="solo immagine", value="solo_immagine"),
        ],
        allineamento=[app_commands.Choice(name=a, value=a) for a in ALLINEAMENTI],
    )
    async def immagine(
        self,
        interaction: discord.Interaction,
        attiva: bool,
        modello: str | None = None,
        sfondo: discord.Attachment | None = None,
        forma_avatar: str | None = None,
        colore_testo: app_commands.Range[str, 4, 7] | None = None,
        titolo: app_commands.Range[str, 1, MAX_TITOLO] | None = None,
        togli_sfondo: bool = False,
        opacita: app_commands.Range[int, 0, 100] | None = None,
        testo: app_commands.Range[str, 1, MAX_TESTO] | None = None,
        ordine: str | None = None,
        allineamento: str | None = None,
        colore_nome: app_commands.Range[str, 4, 11] | None = None,
        trasparente: bool | None = None,
        larghezza: app_commands.Range[int, MISURA_MIN, MISURA_MAX] | None = None,
        altezza: app_commands.Range[int, MISURA_MIN, MISURA_MAX] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return
        colore = None
        if colore_testo is not None:
            colore = colore_valido(colore_testo)
            if colore is None:
                await interaction.response.send_message(
                    await testo_per(interaction, "greetings_il_colore_va_scritto_come"), ephemeral=True
                )
                return
        nome_colore = None
        if colore_nome is not None and colore_nome.lower() != "predefinito":
            nome_colore = colore_valido(colore_nome)
            if nome_colore is None:
                await interaction.response.send_message(
                    await testo_per(interaction, "greetings_il_colore_va_scritto_come"), ephemeral=True
                )
                return
        if sfondo is not None:
            if sfondo.size > MAX_SFONDO_BYTE:
                await interaction.response.send_message(
                    await testo_per(interaction, "greetings_lo_sfondo_pesa_troppo_il"), ephemeral=True
                )
                return
            if not (sfondo.content_type or "").startswith("image/"):
                await interaction.response.send_message(await testo_per(interaction, "greetings_lo_sfondo_deve_essere_un"), ephemeral=True)
                return
        # Il lavoro con l'immagine può durare qualche secondo.
        await interaction.response.defer(ephemeral=True)
        pronto = None
        if sfondo is not None:
            try:
                pronto = await run_image_task(prepara_sfondo, await sfondo.read())
            except ImmagineTroppoGrande:
                await interaction.followup.send(
                    await testo_per(interaction, "greetings_lo_sfondo_ha_troppi_pixel"), ephemeral=True
                )
                return
            except SandboxNonDisponibile:
                await interaction.followup.send(await testo_per(interaction, "err_sandbox_non_disponibile"), ephemeral=True)
                return
            except Exception:
                await interaction.followup.send(
                    await testo_per(interaction, "greetings_non_riesco_ad_aprire_lo"), ephemeral=True
                )
                return
        attuale = await greetings_repo.get_config(guild.id)
        await greetings_repo.set_welcome_image(
            guild.id,
            enabled=attiva,
            template=modello or attuale.welcome_image_template,
            shape=forma_avatar or attuale.welcome_image_shape,
            color=colore or attuale.welcome_image_color,
            title=titolo or attuale.welcome_image_title,
        )
        if any(v is not None for v in (opacita, testo, ordine, allineamento, colore_nome)):
            # RUO-004, 007, 008, 010: ciò che non si indica resta com'è
            await greetings_repo.set_welcome_image_extra(
                guild.id,
                attuale.welcome_image_opacity if opacita is None else opacita,
                attuale.welcome_image_text if testo is None else ("" if testo.lower() == "togli" else testo),
                ordine or attuale.welcome_image_order,
                allineamento or attuale.welcome_image_align,
                attuale.welcome_image_name_color if colore_nome is None else (nome_colore or ""),
            )
        if any(v is not None for v in (trasparente, larghezza, altezza)):  # RUO-005
            await greetings_repo.set_welcome_image_misure(
                guild.id,
                attuale.welcome_image_width if larghezza is None else larghezza,
                attuale.welcome_image_height if altezza is None else altezza,
                attuale.welcome_image_transparent if trasparente is None else trasparente,
            )
        if pronto is not None:
            await greetings_repo.set_welcome_background(guild.id, pronto)
        elif togli_sfondo:
            await greetings_repo.clear_welcome_background(guild.id)
        avviso = ""
        if attiva and not attuale.welcome_enabled:
            avviso = " Il benvenuto però è spento: attivalo con `/admin-benvenuto messaggio`."
        await interaction.followup.send(
            f"Immagine di benvenuto {'attivata' if attiva else 'disattivata'}.{avviso}", ephemeral=True
        )

    @comando_di_gruppo(
        "admin-benvenuto",
        nome="embed",
        descrizione="Usa un embed salvato per il benvenuto, il DM o l'addio.",
    )
    @app_commands.describe(
        dove="Quale messaggio esce con l'embed",
        nome="Il nome dell'embed salvato (o «togli» per non usarne più)",
    )
    @app_commands.choices(dove=[app_commands.Choice(name=d, value=d) for d in DOVE])
    @app_commands.autocomplete(nome=_completa_embed)
    async def embed_cmd(
        self, interaction: discord.Interaction, dove: str, nome: app_commands.Range[str, 1, MAX_NOME_EMBED]
    ) -> None:
        """RUO-001, 014, 015: i segnaposto dell'embed si sostituiscono a ogni invio; un embed non più valido si salta."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if dove not in DOVE:
            await interaction.response.send_message(await testo_per(interaction, "modmail_scelta_non_valida"), ephemeral=True)
            return
        nome = nome.strip().lower()
        if nome == TOGLI:
            await greetings_repo.set_embed(guild.id, dove, "")
            await interaction.response.send_message("Fatto: da ora quel messaggio esce senza embed.", ephemeral=True)
            return
        if await saved_embed_repo.get(guild.id, nome) is None:
            await interaction.response.send_message(
                "Non trovo un embed salvato con quel nome: crealo con `/admin-messaggi embed`.", ephemeral=True
            )
            return
        await greetings_repo.set_embed(guild.id, dove, nome)
        avviso = " Il DM esce solo se è acceso con `/admin-benvenuto messaggio`." if dove == "dm" else ""
        await interaction.response.send_message(f"Fatto: l'embed «{nome}» sarà usato.{avviso}", ephemeral=True)

    @comando_di_gruppo(
        "admin-benvenuto",
        nome="avviso-topic",
        descrizione="Avvisa in un canale quando cambia l'argomento di un canale.",
    )
    @app_commands.describe(canale="Dove mandare l'avviso (se non lo indichi, gli avvisi si spengono)")
    async def avviso_topic(
        self, interaction: discord.Interaction, canale: discord.TextChannel | None = None
    ) -> None:
        """RUO-027: gli avvisi escono solo per i canali che @everyone vede, senza menzioni, uno al minuto per canale."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        await greetings_repo.set_topic_notice(guild.id, canale.id if canale else None)
        await interaction.response.send_message(
            f"Avvisi sull'argomento: {canale.mention}." if canale else "Avvisi sull'argomento spenti.",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "admin-benvenuto",
        nome="anteprima",
        descrizione="Mostra un'anteprima di come apparirebbe un messaggio.",
    )
    @app_commands.describe(kind="Quale messaggio vedere in anteprima")
    @app_commands.choices(
        kind=[
            app_commands.Choice(name="Welcome", value="welcome"),
            app_commands.Choice(name="Goodbye", value="goodbye"),
            app_commands.Choice(name="Boost", value="boost"),
        ]
    )
    async def preview(self, interaction: discord.Interaction, kind: app_commands.Choice[str]) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return

        config = await greetings_repo.get_config(guild.id)
        template = {
            "welcome": config.welcome_message,
            "goodbye": config.goodbye_message,
            "boost": config.boost_message,
        }[kind.value]

        # M 10.2: un testo salvato prima del controllo (o allungato da un
        # cambio di nome del server) non deve far fallire l'anteprima.
        try:
            testo = _render_for_member(template, interaction.user)
        except Exception:
            logger.exception("Anteprima del messaggio non riuscita nel server %s.", guild.id)
            await interaction.response.send_message(
                await testo_per(interaction, "greetings_non_riesco_mostrare_anteprima_di"), ephemeral=True
            )
            return
        if kind.value == "welcome" and config.welcome_image_enabled:
            await interaction.response.defer(ephemeral=True)
            allegato = await _file_benvenuto(config, interaction.user)
            await interaction.followup.send(
                taglia_messaggio(f"Anteprima:\n\n{testo}"),
                ephemeral=True,
                allowed_mentions=menzioni_ammesse(False),
                **({"file": allegato} if allegato is not None else {}),
            )
            return
        await interaction.response.send_message(
            taglia_messaggio(f"Anteprima:\n\n{testo}"),
            ephemeral=True,
            allowed_mentions=menzioni_ammesse(False),
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_GREETINGS,
            display_name="Greetings",
            category="utility",
            description="Messaggi di benvenuto, addio e boost con segnaposto personalizzabili.",
            premium_capable=False,
        )
    )
    await bot.add_cog(GreetingsCog(bot))
