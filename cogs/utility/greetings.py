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

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.admin_mentions_logic import (
    menzioni_ammesse,
    taglia_messaggio,
    utente_puo_pingare_ruoli,
)
from core.leveling_logic import colore_valido
from core.greetings_logic import (
    MAX_MESSAGE_LENGTH,
    analizza_reazioni,
    analizza_varianti,
    lunghezza_dopo_segnaposto,
    render_template,
    scegli_testo,
)
from core import greetings_uscite_logic as uscite
from core.ui_base import BaseModal, BaseView
from core.premium import PremiumModule, registry
from core.repositories.greetings_repo import greetings_repo
from core.safe_image import ImmagineTroppoGrande, run_image_task
from core.security_raid_state import raid_in_corso
from core.welcome_image import (
    FORME,
    MAX_SFONDO_BYTE,
    MAX_TITOLO,
    MODELLI,
    DatiBenvenuto,
    prepara_sfondo,
    render_welcome_image,
)

logger = logging.getLogger("iyokai.greetings")

MODULE_GREETINGS = "greetings"


def _render_for_member(template: str, member: discord.Member) -> str:
    return render_template(
        template,
        user_mention=member.mention,
        username=discord.utils.escape_mentions(member.name),
        server_name=discord.utils.escape_mentions(member.guild.name),
        member_count=member.guild.member_count or 0,
        user_id=member.id,
        display_name=discord.utils.escape_mentions(member.display_name),
        server_id=member.guild.id,
    )


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

    def __init__(self, config) -> None:
        super().__init__()
        self.dm.default = config.welcome_dm_message or None
        self.varianti.default = "\n".join(config.welcome_variants)[:4000] or None
        self.reazioni.default = " ".join(config.welcome_reactions) or None
        self.ban.default = config.ban_message or None

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
        for testo in ([dm] if dm else []) + varianti + ([ban] if ban else []):
            if errore is None and "<@&" in testo and not utente_puo_pingare_ruoli(interaction.user):
                errore = "Per citare un ruolo serve il permesso «Menziona tutti»."
            if errore is None:
                errore = _errore_lunghezza(guild, testo)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await greetings_repo.set_welcome_extra(guild.id, dm, varianti, reazioni, ban)
        await interaction.response.send_message(
            f"Salvato: DM {'con testo suo' if dm else 'come il canale'}, "
            f"{len(varianti)} varianti, {len(reazioni)} reazioni, ban {'con testo suo' if ban else 'con il testo di base'}.",
            ephemeral=True,
        )


async def _invia_con_grafica(channel, testo, grafica, menzioni, guild_id: int, nome: str) -> None:
    """D37: testo più grafica (link https o file). Se la grafica non passa, il testo parte lo stesso."""
    url, immagine, nome_file = grafica if grafica else (None, None, None)
    try:
        try:
            if url:
                embed = discord.Embed()
                embed.set_image(url=url)
                await channel.send(testo, embed=embed, allowed_mentions=menzioni)
            elif immagine:
                file = discord.File(io.BytesIO(immagine), filename=nome_file or "grafica.png")
                await channel.send(testo, file=file, allowed_mentions=menzioni)
            else:
                await channel.send(testo, allowed_mentions=menzioni)
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
            await interaction.response.send_message("Scelta non valida.", ephemeral=True)
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
            avviso = " Il canale dell'addio però non è attivo: configuralo con `/gestione benvenuto addio`."
        await interaction.followup.send(f"Salvato: escono {uscite.ETICHETTE_MODO[modo]}.{avviso}", ephemeral=True)


class ExtraBenvenutoView(BaseView):
    """`/gestione benvenuto extra`: due finestre, i testi del benvenuto e quella di ban e addio (D37)."""

    def __init__(self, config) -> None:
        super().__init__(timeout=300)
        self._config = config

    @discord.ui.button(label="Testi e reazioni", style=discord.ButtonStyle.primary)
    async def testi(self, interaction: discord.Interaction, _bottone: discord.ui.Button) -> None:
        await interaction.response.send_modal(ExtraBenvenutoModal(self._config))

    @discord.ui.button(label="Ban e addio", style=discord.ButtonStyle.secondary)
    async def ban_addio(self, interaction: discord.Interaction, _bottone: discord.ui.Button) -> None:
        await interaction.response.send_modal(UsciteModal(self._config))


async def _file_benvenuto(config, member: discord.Member) -> discord.File | None:
    """NF-11: l'immagine di benvenuto, o None se spenta o non disegnabile (il testo parte lo stesso)."""
    if not config.welcome_image_enabled:
        return None
    try:
        try:
            avatar = await member.display_avatar.replace(size=256, format="png").read()
        except (discord.HTTPException, AttributeError):
            avatar = None
        sfondo = (
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
        )
        png = await run_image_task(render_welcome_image, dati, avatar, sfondo)
    except Exception:
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


class GreetingsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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

        testo = taglia_messaggio(
            _render_for_member(scegli_testo(config.welcome_message, config.welcome_variants), member)
        )
        testo_dm = (
            taglia_messaggio(_render_for_member(config.welcome_dm_message, member))
            if config.welcome_dm_message
            else testo
        )
        menzioni = menzioni_ammesse(config.welcome_ping_ruoli)

        if config.welcome_channel_id is not None:
            channel = member.guild.get_channel(config.welcome_channel_id)
            if isinstance(channel, discord.TextChannel):
                # Durante un raid solo testo: disegnare un'immagine per ogni ingresso è lavoro sprecato.
                puo_allegare = channel.permissions_for(member.guild.me).attach_files
                allegato = (
                    None
                    if raid_in_corso(member.guild.id) or not puo_allegare
                    else await _file_benvenuto(config, member)
                )
                try:
                    try:
                        if allegato is not None:
                            inviato = await channel.send(testo, file=allegato, allowed_mentions=menzioni)
                        else:
                            inviato = await channel.send(testo, allowed_mentions=menzioni)
                    except discord.HTTPException:
                        if allegato is None:
                            raise
                        # L'immagine non è passata (permessi cambiati, file rifiutato): il testo parte lo stesso.
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
                await member.send(testo_dm, allowed_mentions=menzioni_ammesse(False))
            except discord.HTTPException:
                pass  # DM chiusi: non è un errore da segnalare, è normale

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
        testo = taglia_messaggio(_render_for_member(config.goodbye_message, member))
        await _invia_con_grafica(
            channel, testo, await greetings_repo.get_grafica(member.guild.id, uscite.TIPO_ADDIO),
            menzioni_ammesse(config.goodbye_ping_ruoli), member.guild.id, "goodbye",
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
        in_raid = raid_in_corso(guild.id)
        uscite.segna_ban(guild.id, user.id, soppresso=in_raid)
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

        testo = taglia_messaggio(_render_for_member(config.boost_message, after))
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
        "gestione",
        nome="benvenuto",
        descrizione="Configura il messaggio di benvenuto.",
        sottogruppo=_SG_BENVENUTO,
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
        channel: discord.TextChannel | None = None,
        message: TestoMessaggio | None = None,
        dm: bool | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
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
                "Specifica un canale per attivare il welcome message.", ephemeral=True
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
            f"Welcome message {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="extra",
        descrizione="Benvenuto: DM, varianti, reazioni; messaggi di ban e addio.",
        sottogruppo=_SG_BENVENUTO,
    )
    async def welcome_extra(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        config = await greetings_repo.get_config(interaction.guild.id)
        await interaction.response.send_message(
            "Cosa vuoi cambiare? Il testo del ban si scrive in «Testi e reazioni» (vuoto = quello di base).",
            view=ExtraBenvenutoView(config), ephemeral=True,
        )

    @comando_di_gruppo(
        "gestione",
        nome="addio",
        descrizione="Configura il messaggio di addio.",
        sottogruppo=_SG_BENVENUTO,
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
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
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
                "Specifica un canale per attivare il goodbye message.", ephemeral=True
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
            f"Goodbye message {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="boost",
        descrizione="Configura il messaggio di boost.",
        sottogruppo=_SG_BENVENUTO,
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
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
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
                "Specifica un canale per attivare il boost message.", ephemeral=True
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
            f"Boost message {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="immagine",
        descrizione="Aggiungi al benvenuto un'immagine con avatar, nome e numero del membro.",
        sottogruppo=_SG_BENVENUTO,
    )
    @app_commands.describe(
        attiva="Attiva o disattiva l'immagine",
        modello="Il modello pronto da usare",
        sfondo="Uno sfondo tuo (immagine sotto 3 MB); sostituisce il modello",
        forma_avatar="Avatar tondo o quadrato",
        colore_testo="Colore del testo, per esempio #FFFFFF",
        titolo="La scritta in alto (massimo 40 caratteri)",
        togli_sfondo="Torna al modello pronto cancellando lo sfondo caricato",
    )
    @app_commands.choices(
        modello=[app_commands.Choice(name=nome, value=nome) for nome in MODELLI],
        forma_avatar=[app_commands.Choice(name=forma, value=forma) for forma in FORME],
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
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        colore = None
        if colore_testo is not None:
            colore = colore_valido(colore_testo)
            if colore is None:
                await interaction.response.send_message(
                    "Il colore va scritto come #RRGGBB, per esempio #FFFFFF.", ephemeral=True
                )
                return
        if sfondo is not None:
            if sfondo.size > MAX_SFONDO_BYTE:
                await interaction.response.send_message(
                    "Lo sfondo pesa troppo: il limite è 3 MB.", ephemeral=True
                )
                return
            if not (sfondo.content_type or "").startswith("image/"):
                await interaction.response.send_message("Lo sfondo deve essere un'immagine.", ephemeral=True)
                return
        # Il lavoro con l'immagine può durare qualche secondo.
        await interaction.response.defer(ephemeral=True)
        pronto = None
        if sfondo is not None:
            try:
                pronto = await run_image_task(prepara_sfondo, await sfondo.read())
            except ImmagineTroppoGrande:
                await interaction.followup.send(
                    "Lo sfondo ha troppi pixel: il limite è 16 megapixel (circa 4000×4000).", ephemeral=True
                )
                return
            except Exception:
                await interaction.followup.send(
                    "Non riesco ad aprire lo sfondo: usa un PNG, JPEG o WebP.", ephemeral=True
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
        if pronto is not None:
            await greetings_repo.set_welcome_background(guild.id, pronto)
        elif togli_sfondo:
            await greetings_repo.clear_welcome_background(guild.id)
        avviso = ""
        if attiva and not attuale.welcome_enabled:
            avviso = " Il benvenuto però è spento: attivalo con `/gestione benvenuto benvenuto`."
        await interaction.followup.send(
            f"Immagine di benvenuto {'attivata' if attiva else 'disattivata'}.{avviso}", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="anteprima",
        descrizione="Mostra un'anteprima di come apparirebbe un messaggio.",
        sottogruppo=_SG_BENVENUTO,
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
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
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
                "Non riesco a mostrare l'anteprima di questo messaggio.", ephemeral=True
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
