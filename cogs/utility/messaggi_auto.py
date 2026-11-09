"""
cogs/utility/messaggi_auto.py
=============================
`/admin-messaggi scrivi` (messaggio del bot da una finestra) e `/admin-messaggi auto`: citazione dei link ai
messaggi, correzione dei link, pubblicazione degli annunci e interruttore dell'accorciatore. I listener
usano la copia in memoria del repository. Le tabelle legate ai canali si puliscono con on_guild_channel_delete.
Funzioni coperte: catalogo #128 UTL-083, 071, 072, 112, 208 (D69, B3)
"""

from __future__ import annotations

import logging
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

from core import channel_router as router
from core import messaggi_auto_logic as logica
from core.admin_mentions_logic import menzioni_ammesse, utente_puo_pingare_ruoli
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_interazione, lingua_server, t
from core.repositories.messaggi_auto_repo import messaggi_auto_repo
from core.repositories.web_repo import web_repo
from core.ui_base import BaseModal

logger = logging.getLogger("iyokai.messaggi_auto")

MAX_SCRIVI = 2000
_LINK_RISPOSTA = re.compile(r"discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")


class ScriviModal(BaseModal):
    def __init__(self, canale: discord.abc.Messageable, rispondi_a: int | None, lingua: str) -> None:
        super().__init__(title=t("scrivi_titolo", lingua)[:45], timeout=600)
        self.canale = canale
        self.rispondi_a = rispondi_a
        self.lingua = lingua
        self.testo = discord.ui.TextInput(
            label=t("scrivi_etichetta", lingua)[:45], style=discord.TextStyle.paragraph, max_length=MAX_SCRIVI
        )
        self.add_item(self.testo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        riferimento = None
        if self.rispondi_a:
            riferimento = discord.MessageReference(
                message_id=self.rispondi_a, channel_id=self.canale.id, fail_if_not_exists=False
            )
        try:
            await self.canale.send(
                self.testo.value[:MAX_SCRIVI],
                reference=riferimento,
                allowed_mentions=menzioni_ammesse(utente_puo_pingare_ruoli(interaction.user)),
            )
        except discord.HTTPException as errore:
            logger.warning("Scrivi: invio fallito in %s: %s", self.canale.id, errore)
            await interaction.response.send_message(t("scrivi_errore", self.lingua), ephemeral=True)
            return
        await interaction.response.send_message(t("scrivi_fatto", self.lingua, canale=self.canale.mention), ephemeral=True)


def id_messaggio_da_link(testo: str | None, guild_id: int, canale_id: int) -> int | None:
    m = _LINK_RISPOSTA.search(testo or "")
    if m and int(m[1]) == guild_id and int(m[2]) == canale_id:
        return int(m[3])
    return None


class MessaggiAutoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.limite = logica.LimitePubblicazioni()

    @comando_di_gruppo("admin-messaggi", nome="scrivi", descrizione="Fai scrivere un messaggio al bot in un canale.")
    @app_commands.describe(canale="Dove scrivere", rispondi_a="Link a un messaggio di quel canale a cui rispondere")
    async def scrivi(
        self, interaction: discord.Interaction, canale: discord.TextChannel, rispondi_a: app_commands.Range[str, 1, 200] | None = None
    ) -> None:
        lingua = await lingua_interazione(interaction)
        guild = interaction.guild
        permessi = canale.permissions_for(guild.me)
        if not (permessi.view_channel and permessi.send_messages):
            await interaction.response.send_message(t("scrivi_senza_permessi", lingua, canale=canale.mention), ephemeral=True)
            return
        if not canale.permissions_for(interaction.user).send_messages:
            await interaction.response.send_message(t("scrivi_tu_senza_permessi", lingua, canale=canale.mention), ephemeral=True)
            return
        await interaction.response.send_modal(
            ScriviModal(canale, id_messaggio_da_link(rispondi_a, guild.id, canale.id), lingua)
        )

    @comando_di_gruppo(
        "admin-messaggi", nome="auto", descrizione="Automatismi: citazioni, correzione link, pubblicazione annunci, accorciatore."
    )
    @app_commands.describe(
        citazioni="Cita i link ai messaggi del server",
        correggi_link="Accendi o spegni la correzione di un dominio (ogni scelta cambia lo stato)",
        pubblica="Un canale annunci i cui messaggi si pubblicano da soli",
        togli_pubblica="Un canale annunci da non pubblicare più",
        accorcia="Permetti /web accorcia in questo server",
    )
    @app_commands.choices(
        correggi_link=[app_commands.Choice(name=logica.etichetta_correzione(d).replace(">", " → "), value=d) for d in logica.CORREZIONI]
        + [app_commands.Choice(name="spegni tutte", value="*")]
    )
    async def auto(
        self,
        interaction: discord.Interaction,
        citazioni: bool | None = None,
        correggi_link: str | None = None,
        pubblica: discord.TextChannel | None = None,
        togli_pubblica: discord.TextChannel | None = None,
        accorcia: bool | None = None,
    ) -> None:
        lingua = await lingua_interazione(interaction)
        gid = interaction.guild.id
        righe: list[str] = []
        if citazioni is not None:
            await messaggi_auto_repo.imposta_citazioni(gid, citazioni)
        if accorcia is not None:
            await web_repo.imposta_accorcia(gid, accorcia)
        if correggi_link == "*":
            await messaggi_auto_repo.spegni_correzioni(gid)
        elif correggi_link in logica.CORREZIONI:
            acceso = await messaggi_auto_repo.alterna_correzione(gid, logica.etichetta_correzione(correggi_link))
            righe.append(t("auto_correzione_acceso" if acceso else "auto_correzione_spento", lingua, dominio=correggi_link))
        if pubblica is not None:
            if not pubblica.is_news():
                righe.append(t("auto_pubblica_non_annunci", lingua, canale=pubblica.mention))
            elif not await messaggi_auto_repo.aggiungi_canale_pubblica(gid, pubblica.id):
                righe.append(t("auto_pubblica_pieno", lingua, massimo=logica.MAX_CANALI_PUBBLICA))
        if togli_pubblica is not None:
            await messaggi_auto_repo.togli_canale_pubblica(gid, togli_pubblica.id)
            self.limite.dimentica(togli_pubblica.id)
        stato = await messaggi_auto_repo.get(gid)
        righe.append(t(
            "auto_stato", lingua,
            citazioni=t("auto_si" if stato.citazioni else "auto_no", lingua),
            correzioni=", ".join(sorted(logica.mappa_correzioni(list(stato.correzioni)))) or "—",
            pubblica=" ".join(f"<#{c}>" for c in stato.pubblica_canali) or "—",
            accorcia=t("auto_si" if await web_repo.accorcia_attivo(gid) else "auto_no", lingua),
        ))
        await interaction.response.send_message(
            "\n".join(righe)[:2000], ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    # ------------------------------------------------------------ ascolto
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return
        try:
            stato = await messaggi_auto_repo.get(message.guild.id)
        except Exception:
            logger.exception("Automatismi: lettura impostazioni fallita")
            return
        if message.channel.id in stato.pubblica_canali:
            await self._pubblica(message)  # anche i messaggi di webhook e di altri bot
        if message.author.bot or not message.content:
            return
        if stato.citazioni:
            await self._cita(message)
        if stato.correzioni:
            corretti = logica.link_corretti(message.content, logica.mappa_correzioni(list(stato.correzioni)))
            if corretti:
                try:
                    await message.reply("\n".join(corretti), mention_author=False, allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    pass

    async def _pubblica(self, message: discord.Message) -> None:
        canale = message.channel
        if not isinstance(canale, discord.TextChannel) or not canale.is_news():
            return
        adesso = time.time()
        if not self.limite.ammessa(canale.id, adesso):
            if self.limite.da_avvisare(canale.id, adesso):
                await self._avvisa_limite(message.guild, canale)
            return
        try:
            await message.publish()
        except discord.HTTPException as errore:
            logger.warning("Pubblicazione di %s in %s fallita: %s", message.id, canale.id, errore)

    async def _avvisa_limite(self, guild: discord.Guild, canale: discord.TextChannel) -> None:
        lingua = await lingua_server(guild.id)
        destinazione = await router.destinazione(guild, router.TIPO_SERVER)
        embed = discord.Embed(
            description=t("auto_pubblica_limite", lingua, canale=canale.mention, n=logica.PUBBLICAZIONI_ALL_ORA)[:4000],
            color=discord.Color.orange(),
        )
        if destinazione is not None:
            await router.invia_a(destinazione, guild, router.TIPO_SERVER, embed=embed)
        else:
            logger.warning("Pubblicazione: limite orario raggiunto in %s", canale.id)

    async def _cita(self, message: discord.Message) -> None:
        guild = message.guild
        embed_da_inviare: list[discord.Embed] = []
        for canale_id, messaggio_id in logica.link_ai_messaggi(message.content, guild.id):
            origine = guild.get_channel_or_thread(canale_id)
            if origine is None or not hasattr(origine, "fetch_message"):
                continue
            permessi_autore = origine.permissions_for(message.author)
            permessi_bot = origine.permissions_for(guild.me)
            if not (permessi_bot.view_channel and permessi_bot.read_message_history):
                continue
            vede = permessi_autore.view_channel and permessi_autore.read_message_history
            if not logica.puo_citare(_nsfw(origine), _nsfw(message.channel), vede):
                continue
            try:
                citato = await origine.fetch_message(messaggio_id)
            except discord.HTTPException:
                continue
            embed = discord.Embed(description=(citato.content or "")[:4096], timestamp=citato.created_at, color=discord.Color.light_grey())
            embed.set_author(name=citato.author.display_name[:256], icon_url=citato.author.display_avatar.url)
            embed.add_field(name="#" + getattr(origine, "name", "?")[:100], value=f"[→]({citato.jump_url})")
            immagine = next((a.url for a in citato.attachments if (a.content_type or "").startswith("image/")), None)
            if immagine:
                embed.set_image(url=immagine)
            embed_da_inviare.append(embed)
        if embed_da_inviare:
            try:
                await message.reply(embeds=embed_da_inviare, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        self.limite.dimentica(channel.id)
        try:
            await messaggi_auto_repo.togli_canale_pubblica(channel.guild.id, channel.id)
        except Exception:
            logger.exception("Automatismi: pulizia del canale %s fallita", channel.id)


def _nsfw(canale) -> bool:
    parente = getattr(canale, "parent", None)
    return bool(getattr(canale, "nsfw", False) or getattr(parente, "nsfw", False))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessaggiAutoCog(bot))
