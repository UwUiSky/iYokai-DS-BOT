"""
cogs/user_app/messaggi.py
=========================
Menu «App» sul messaggio (tasto destro) di iYokai App (SPEC §B.2): Traduci, Salva nei segnalibri, Ricordamelo,
Citazione come immagine, Meme da questa immagine, Controlla i link, Segnala alla rete iYokai, Spiega o riassumi;
più `/segnalibri elenco|rimuovi`. Ogni comando risponde una volta sola (dove l'app non è nel server Discord ne
ammette 5 in tutto). Si carica solo sul client dell'app (core/user_app_bot.py).
Funzioni coperte: SPEC §B.2 (NF-36, #107)
Dipende da: core/user_app_messaggi.py, core/user_app_ai.py, core/support_service.py
"""

from __future__ import annotations

import io

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.duration_logic import format_duration, parse_duration
from core.i18n import lingua_interazione, t, testo_per
from core.meme_logic import render_meme
from core.phishing_list_fetcher import lista_phishing
from core.repositories.user_app_repo import MAX_SEGNALIBRI, user_app_repo
from core.safe_image import MAX_IMAGE_BYTES, run_image_task
from core.support_service import SupportoNonAttivo, TroppeRichieste, apri_richiesta
from core.ui_base import BaseModal
from core.user_app_ai import chiedi_ai_app
from core.user_app_bot import e_istanza_app
from core.user_app_impostazioni import impostazioni_di, risposta_privata
from core.user_app_logic import errore_durata, programma_promemoria
from core.user_app_messaggi import (
    STATO_ACCORCIATORE,
    STATO_LISTA,
    STATO_SOSPETTO,
    citazione_png,
    controlla_link,
    istruzioni_ai,
    testo_segnalazione,
    testo_segnalibro,
)

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)
NESSUNA_MENZIONE = discord.AllowedMentions.none()
SOGLIA_RIASSUNTO = 800
RIGHE_PER_PAGINA = 10
NOMI_MENU = (
    "Traduci", "Salva nei segnalibri", "Ricordamelo", "Citazione come immagine", "Meme da questa immagine",
    "Controlla i link", "Segnala alla rete iYokai", "Spiega o riassumi",
)


def testo_del_messaggio(messaggio: discord.Message) -> str:
    """Il testo scritto; se non c'è, la descrizione del primo embed."""
    if messaggio.content:
        return messaggio.content
    for embed in messaggio.embeds:
        if embed.description:
            return embed.description
    return ""


def link_messaggio(guild_id: int | None, channel_id: int, message_id: int) -> str:
    return f"https://discord.com/channels/{guild_id or '@me'}/{channel_id}/{message_id}"


def prima_immagine(messaggio: discord.Message) -> discord.Attachment | None:
    for allegato in messaggio.attachments:
        if (allegato.content_type or "").startswith("image/") and allegato.size <= MAX_IMAGE_BYTES:
            return allegato
    return None


class RicordamiModal(BaseModal):
    def __init__(self, link: str, testo: str, lingua: str = "it") -> None:
        super().__init__(title=t("app_menu_ricordamelo", lingua)[:45])
        self.link, self.testo = link, testo
        self.durata = discord.ui.TextInput(label=t("app_ricorda_durata", lingua)[:45], default="2h", min_length=2, max_length=10)
        self.add_item(self.durata)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            secondi = parse_duration(self.durata.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        errore = errore_durata(secondi)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        if not (await impostazioni_di(interaction.user.id)).dm_ok:
            await interaction.response.send_message(await testo_per(interaction, "app_dm_spenti"), ephemeral=True)
            return
        numero = await programma_promemoria(interaction.user.id, secondi, f"{self.testo}\n{self.link}")
        chiave = "app_promemoria_creato" if numero else "app_promemoria_troppi"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, durata=format_duration(secondi), numero=numero, massimo=25), ephemeral=True
        )


class MemeModal(BaseModal):
    def __init__(self, allegato: discord.Attachment, lingua: str = "it") -> None:
        super().__init__(title=t("app_menu_meme", lingua)[:45])
        self.allegato = allegato
        self.alto = discord.ui.TextInput(label=t("app_meme_alto", lingua)[:45], required=False, max_length=100)
        self.basso = discord.ui.TextInput(label=t("app_meme_basso", lingua)[:45], required=False, max_length=100)
        self.add_item(self.alto)
        self.add_item(self.basso)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not self.alto.value and not self.basso.value:
            await interaction.response.send_message(await testo_per(interaction, "app_meme_serve_testo"), ephemeral=True)
            return
        privata = await risposta_privata(interaction.user.id)
        await interaction.response.defer(ephemeral=privata)
        try:
            dati = await self.allegato.read()
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "app_immagine_non_scaricata"), ephemeral=True)
            return
        png = await run_image_task(render_meme, dati, self.alto.value, self.basso.value)
        if png is None:
            await interaction.followup.send(await testo_per(interaction, "app_immagine_non_elaborata"), ephemeral=True)
            return
        await interaction.followup.send(file=discord.File(io.BytesIO(png), filename="meme.png"), ephemeral=privata)


class SegnalaModal(BaseModal):
    def __init__(self, messaggio: discord.Message, client_staff: discord.Client | None, lingua: str = "it") -> None:
        super().__init__(title=t("app_menu_segnala", lingua)[:45])
        self.messaggio, self.client_staff = messaggio, client_staff
        self.motivo = discord.ui.TextInput(
            label=t("app_segnala_motivo", lingua)[:45], style=discord.TextStyle.paragraph, min_length=5, max_length=300
        )
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        m = self.messaggio
        if self.client_staff is None:
            await interaction.response.send_message(await testo_per(interaction, "app_assistenza_spenta"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        corpo = testo_segnalazione(
            m.author.id, m.author.display_name, link_messaggio(m.guild.id if m.guild else None, m.channel.id, m.id),
            testo_del_messaggio(m), self.motivo.value,
        )
        try:
            aperta = await apri_richiesta(
                self.client_staff, config.SUPPORT_CHANNEL_ID, interaction.user.id, interaction.user.display_name,
                f"Segnalazione rete: {m.author.display_name}"[:80], corpo,
            )
        except TroppeRichieste:
            await interaction.followup.send(await testo_per(interaction, "app_assistenza_troppe"), ephemeral=True)
        except SupportoNonAttivo:
            await interaction.followup.send(await testo_per(interaction, "app_assistenza_spenta"), ephemeral=True)
        else:
            await interaction.followup.send(await testo_per(interaction, "app_segnalazione_inviata", numero=aperta.numero), ephemeral=True)


class MessaggiCog(commands.Cog):
    segnalibri = app_commands.Group(
        name="segnalibri", description="I messaggi che hai salvato, in ogni server e in DM.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        callback = (
            self.menu_traduci, self.menu_segnalibro, self.menu_ricordamelo, self.menu_citazione, self.menu_meme,
            self.menu_link, self.menu_segnala, self.menu_spiega,
        )
        self._menu = [
            app_commands.ContextMenu(name=nome, callback=cb, allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE)
            for nome, cb in zip(NOMI_MENU, callback)
        ]
        for menu in self._menu:
            bot.tree.add_command(menu)

    async def cog_unload(self) -> None:
        for menu in self._menu:
            self.bot.tree.remove_command(menu.name, type=menu.type)

    # ---------------------------------------------------------------- AI: traduci, spiega
    async def _con_ai(self, interaction: discord.Interaction, messaggio: discord.Message, funzione: str, tipo: str) -> None:
        testo = testo_del_messaggio(messaggio)
        if not testo.strip():
            await interaction.response.send_message(await testo_per(interaction, "app_msg_senza_testo"), ephemeral=True)
            return
        lingua = await lingua_interazione(interaction)
        if funzione == "spiega" and len(testo) > SOGLIA_RIASSUNTO:
            funzione = "riassumi"
        await interaction.response.defer(ephemeral=True)
        risposta, motivo = await chiedi_ai_app(
            interaction.user.id, f"app_{funzione}", tipo, testo, istruzioni_ai(funzione, lingua), lingua
        )
        await interaction.followup.send((risposta or motivo or "")[:2000], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    async def menu_traduci(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        await self._con_ai(interaction, messaggio, "traduci", "traduzione")

    async def menu_spiega(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        await self._con_ai(interaction, messaggio, "spiega", "testo")

    # ---------------------------------------------------------------- segnalibri
    async def menu_segnalibro(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        testo = testo_segnalibro(testo_del_messaggio(messaggio)) or t("app_segnalibro_senza_testo", await lingua_interazione(interaction))
        numero = await user_app_repo.salva_segnalibro(
            interaction.user.id, messaggio.guild.id if messaggio.guild else None, messaggio.channel.id, messaggio.id,
            messaggio.author.display_name[:80], testo,
        )
        if numero is None:
            await interaction.response.send_message(
                await testo_per(interaction, "app_segnalibri_pieni", massimo=MAX_SEGNALIBRI), ephemeral=True
            )
            return
        await interaction.response.send_message(await testo_per(interaction, "app_segnalibro_salvato", numero=numero), ephemeral=True)

    @segnalibri.command(name="elenco", description="Mostra i tuoi segnalibri, i più recenti prima.")
    @app_commands.describe(dopo="Il numero dell'ultimo che hai già visto (per la pagina dopo)")
    async def elenco(self, interaction: discord.Interaction, dopo: app_commands.Range[int, 0, 2_147_483_647] = 0) -> None:
        righe = await user_app_repo.segnalibri(interaction.user.id, RIGHE_PER_PAGINA + 1, dopo)
        lingua = await lingua_interazione(interaction)
        if not righe:
            await interaction.response.send_message(t("app_segnalibri_nessuno", lingua), ephemeral=True)
            return
        altre = len(righe) > RIGHE_PER_PAGINA
        righe = righe[:RIGHE_PER_PAGINA]
        corpo = "\n".join(
            f"`{r['id']}` · **{r['autore'][:40]}**: {r['testo'][:90]} · "
            f"[{t('app_segnalibri_vai', lingua)}]({link_messaggio(r['guild_id'], r['channel_id'], r['message_id'])})"
            for r in righe
        )
        embed = discord.Embed(title=t("app_segnalibri_titolo", lingua), description=corpo[:4000], color=discord.Color.blurple())
        if altre:
            embed.set_footer(text=t("app_segnalibri_altri", lingua, ultimo=righe[-1]["id"]))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @segnalibri.command(name="rimuovi", description="Toglie un segnalibro.")
    @app_commands.describe(numero="Il numero del segnalibro (da /segnalibri elenco)")
    async def rimuovi(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_147_483_647]) -> None:
        chiave = "app_segnalibro_tolto" if await user_app_repo.rimuovi_segnalibro(interaction.user.id, numero) else "app_segnalibro_non_trovato"
        await interaction.response.send_message(await testo_per(interaction, chiave, numero=numero), ephemeral=True)

    # ---------------------------------------------------------------- ricordamelo, citazione, meme
    async def menu_ricordamelo(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        testo = f"📌 {testo_segnalibro(testo_del_messaggio(messaggio))[:200]}".strip()
        link = link_messaggio(messaggio.guild.id if messaggio.guild else None, messaggio.channel.id, messaggio.id)
        await interaction.response.send_modal(RicordamiModal(link, testo, await lingua_interazione(interaction)))

    async def menu_citazione(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        testo = testo_del_messaggio(messaggio)
        if not testo.strip():
            await interaction.response.send_message(await testo_per(interaction, "app_msg_senza_testo"), ephemeral=True)
            return
        privata = await risposta_privata(interaction.user.id)
        await interaction.response.defer(ephemeral=privata)
        try:
            avatar = await messaggio.author.display_avatar.read()
        except discord.HTTPException:
            avatar = None
        png = await run_image_task(citazione_png, testo, messaggio.author.display_name, avatar)
        await interaction.followup.send(file=discord.File(io.BytesIO(png), filename="citazione.png"), ephemeral=privata)

    async def menu_meme(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        allegato = prima_immagine(messaggio)
        if allegato is None:
            await interaction.response.send_message(await testo_per(interaction, "app_msg_senza_immagine"), ephemeral=True)
            return
        await interaction.response.send_modal(MemeModal(allegato, await lingua_interazione(interaction)))

    # ---------------------------------------------------------------- controlla i link, segnala
    async def menu_link(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        lista_phishing.aggiorna_se_serve()
        esiti = controlla_link(testo_del_messaggio(messaggio), lista_phishing.domini)
        lingua = await lingua_interazione(interaction)
        if not esiti:
            await interaction.response.send_message(t("app_link_nessuno", lingua), ephemeral=True)
            return
        simbolo = {STATO_LISTA: "🚨", STATO_SOSPETTO: "⚠️", STATO_ACCORCIATORE: "🔗"}
        righe = [f"{simbolo.get(e.stato, '✅')} `{e.dominio[:60]}`: {t('app_link_' + e.stato, lingua)}" for e in esiti]
        righe.append(t("app_link_nota", lingua))
        await interaction.response.send_message("\n".join(righe)[:2000], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    async def menu_segnala(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        if messaggio.author.id == interaction.user.id:
            await interaction.response.send_message(await testo_per(interaction, "app_segnala_te_stesso"), ephemeral=True)
            return
        await interaction.response.send_modal(
            SegnalaModal(messaggio, getattr(self.bot, "bot_principale", None), await lingua_interazione(interaction))
        )


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app: il bot principale non riceve questi comandi."""
    if e_istanza_app(bot):
        await bot.add_cog(MessaggiCog(bot))
