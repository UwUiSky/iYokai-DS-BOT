"""
cogs/utility/strumenti_server.py
================================
Strumenti del server per lo staff e per tutti: `/mod-canali espressione` (emoji o sticker da un allegato o da
un'emoji di un messaggio), `/mod-canali thread` (crea, archivia, elimina) e `/voice vai` (spostarsi in un vocale dove si
può entrare). Si controlla il permesso Discord di chi scrive, non solo il livello del bot.
Funzioni coperte: catalogo #128 UTL-209, 210, 211 (D69, B17)
"""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per
from core.safe_image import ImmagineTroppoGrande, run_image_task, safe_open_image
from core.strumenti_server_logic import (
    AZIONI_THREAD, TIPI_ESPRESSIONE, nome_emoji_valido, nome_sticker_valido, posti_emoji_liberi, posti_sticker_liberi,
    puo_entrare_nel_vocale, trova_emoji, troppo_pesante,
)
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.strumenti_server")

_NESSUNA_MENZIONE = discord.AllowedMentions.none()
SECONDI_CONFERMA = 60
_SCELTE_TIPO = [app_commands.Choice(name=n, value=n) for n in TIPI_ESPRESSIONE]
_SCELTE_THREAD = [app_commands.Choice(name=n, value=n) for n in AZIONI_THREAD]


class ConfermaEliminaThread(BaseView):
    """Eliminare un thread non si può disfare: serve la conferma di chi ha dato il comando, e il permesso si ricontrolla al tasto."""

    def __init__(self, proprietario: int, thread: discord.Thread, etichette: tuple[str, str]) -> None:
        super().__init__(timeout=SECONDI_CONFERMA)
        self.proprietario, self.thread = proprietario, thread
        self.conferma.label, self.annulla.label = etichette[0][:80], etichette[1][:80]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()  # anti-doppio-clic prima di ogni await
        if not self.thread.permissions_for(interaction.user).manage_threads:
            await interaction.response.edit_message(content=await testo_per(interaction, "strumenti_thread_permesso"), view=None)
            return
        try:
            await self.thread.delete(reason=f"Eliminato da {interaction.user} ({interaction.user.id})")
        except discord.HTTPException:
            await interaction.response.edit_message(content=await testo_per(interaction, "strumenti_non_riuscito"), view=None)
            return
        await interaction.response.edit_message(content=await testo_per(interaction, "strumenti_thread_eliminato"), view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_togli_annullato"), view=None)


class StrumentiServerCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _dire(self, interaction: discord.Interaction, chiave: str, **valori) -> None:
        testo = await testo_per(interaction, chiave, **valori)
        inviare = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await inviare(testo, ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    # ------------------------------------------------------------ emoji e sticker (UTL-209)
    @comando_di_gruppo("mod-canali", nome="espressione", descrizione="Aggiungi un'emoji o uno sticker al server da un file o da un'emoji.")
    @app_commands.describe(
        tipo="Emoji o sticker", nome="Il nome (emoji: lettere, numeri e _, da 2 a 32; sticker: da 2 a 30 caratteri)",
        file="L'immagine (PNG, JPG o GIF)", emoji="Oppure un'emoji di un altro server, scritta qui",
        emoji_associata="Solo sticker: l'emoji che lo richiama (di base 🙂)",
    )
    @app_commands.choices(tipo=_SCELTE_TIPO)
    async def espressione(
        self, interaction: discord.Interaction, tipo: app_commands.Choice[str], nome: app_commands.Range[str, 2, 32],
        file: discord.Attachment | None = None, emoji: app_commands.Range[str, 1, 100] | None = None,
        emoji_associata: app_commands.Range[str, 1, 8] = "🙂",
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await self._dire(interaction, "guild_only_command")
            return
        if not (interaction.permissions.create_expressions or interaction.permissions.administrator):
            await self._dire(interaction, "strumenti_manca_permesso", permesso="create_expressions")
            return
        if not guild.me.guild_permissions.create_expressions:
            await self._dire(interaction, "strumenti_bot_manca_permesso", permesso="create_expressions")
            return
        genere = tipo.value
        if not (nome_emoji_valido(nome) if genere == "emoji" else nome_sticker_valido(nome)):
            await self._dire(interaction, "strumenti_nome_non_valido")
            return
        trovata = trova_emoji(emoji) if emoji else None
        if (file is None) == (trovata is None):
            await self._dire(interaction, "strumenti_serve_una_fonte")
            return
        if file is not None and troppo_pesante(genere, file.size):
            await self._dire(interaction, "strumenti_troppo_pesante", kb=256 if genere == "emoji" else 512)
            return
        animata = trovata.animata if trovata else (file.filename.lower().endswith(".gif"))
        if genere == "emoji" and posti_emoji_liberi(guild, animata) == 0:
            await self._dire(interaction, "strumenti_posti_finiti")
            return
        if genere == "sticker" and posti_sticker_liberi(guild) == 0:
            await self._dire(interaction, "strumenti_posti_finiti")
            return
        await interaction.response.defer(ephemeral=True)
        try:
            if file is not None:
                dati = await file.read()
            else:  # l'immagine si scarica dalla rete di Discord con l'ID, mai da un indirizzo scritto dall'utente
                dati = await discord.PartialEmoji(name=trovata.nome, animated=trovata.animata, id=trovata.id).read()
            if troppo_pesante(genere, len(dati)):
                await self._dire(interaction, "strumenti_troppo_pesante", kb=256 if genere == "emoji" else 512)
                return
            await run_image_task(safe_open_image, dati)  # dimensioni e formato controllati prima di mandarla a Discord
            motivo = f"Aggiunta da {interaction.user} ({interaction.user.id})"
            if genere == "emoji":
                creata = await guild.create_custom_emoji(name=nome, image=dati, reason=motivo)
                await interaction.followup.send(f"{creata} {nome}", ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)
            else:
                await guild.create_sticker(
                    name=nome, description=nome, emoji=emoji_associata, file=discord.File(io.BytesIO(dati), filename="sticker.png"), reason=motivo)
                await self._dire(interaction, "strumenti_sticker_creato", nome=nome)
        except (ImmagineTroppoGrande, OSError, ValueError):
            await self._dire(interaction, "strumenti_immagine_non_valida")
        except discord.NotFound:
            await self._dire(interaction, "strumenti_emoji_non_trovata")
        except discord.HTTPException:
            logger.warning("Emoji o sticker non creato.", exc_info=True)
            await self._dire(interaction, "strumenti_non_riuscito")

    # ------------------------------------------------------------ thread (UTL-210)
    @comando_di_gruppo("mod-canali", nome="thread", descrizione="Crea, archivia o elimina un thread.")
    @app_commands.describe(
        azione="Cosa fare", nome="Il nome del nuovo thread (solo «crea»)", canale="Il canale dove crearlo (di base quello attuale)",
        thread="Il thread da archiviare o eliminare (di base quello attuale)",
    )
    @app_commands.choices(azione=_SCELTE_THREAD)
    async def thread(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str], nome: app_commands.Range[str, 1, 100] | None = None,
        canale: discord.TextChannel | None = None, thread: discord.Thread | None = None,
    ) -> None:
        if interaction.guild is None:
            await self._dire(interaction, "guild_only_command")
            return
        if azione.value == "crea":
            sede = canale or (interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None)
            if sede is None or nome is None:
                await self._dire(interaction, "strumenti_thread_serve_nome")
                return
            if not sede.permissions_for(interaction.user).create_public_threads:
                await self._dire(interaction, "strumenti_manca_permesso", permesso="create_public_threads")
                return
            if not sede.permissions_for(interaction.guild.me).create_public_threads:
                await self._dire(interaction, "strumenti_bot_manca_permesso", permesso="create_public_threads")
                return
            try:
                nuovo = await sede.create_thread(name=nome, type=discord.ChannelType.public_thread, reason=f"Creato da {interaction.user} ({interaction.user.id})")
            except discord.HTTPException:
                await self._dire(interaction, "strumenti_non_riuscito")
                return
            await interaction.response.send_message(nuovo.mention, ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)
            return
        bersaglio = thread or (interaction.channel if isinstance(interaction.channel, discord.Thread) else None)
        if bersaglio is None:
            await self._dire(interaction, "strumenti_thread_quale")
            return
        if not bersaglio.permissions_for(interaction.user).manage_threads:
            await self._dire(interaction, "strumenti_manca_permesso", permesso="manage_threads")
            return
        if not bersaglio.permissions_for(interaction.guild.me).manage_threads:
            await self._dire(interaction, "strumenti_bot_manca_permesso", permesso="manage_threads")
            return
        if azione.value == "archivia":
            try:
                await bersaglio.edit(archived=True, reason=f"Archiviato da {interaction.user} ({interaction.user.id})")
            except discord.HTTPException:
                await self._dire(interaction, "strumenti_non_riuscito")
                return
            await self._dire(interaction, "strumenti_thread_archiviato")
            return
        etichette = (await testo_per(interaction, "conteggio_togli_bottone"), await testo_per(interaction, "conteggio_togli_annulla"))
        await interaction.response.send_message(
            await testo_per(interaction, "strumenti_thread_elimina_chiedi", nome=bersaglio.name[:100]), ephemeral=True,
            allowed_mentions=_NESSUNA_MENZIONE, view=ConfermaEliminaThread(interaction.user.id, bersaglio, etichette))

    # ------------------------------------------------------------ andare in un vocale (UTL-211)
    @comando_di_gruppo("voice", nome="vai", descrizione="Spostati in un vocale dove puoi entrare.")
    @app_commands.describe(canale="Il vocale dove andare")
    async def vai(self, interaction: discord.Interaction, canale: discord.VoiceChannel | discord.StageChannel) -> None:
        guild = interaction.guild
        membro = interaction.user
        if guild is None or not isinstance(membro, discord.Member):
            await self._dire(interaction, "guild_only_command")
            return
        if membro.voice is None or membro.voice.channel is None:
            await self._dire(interaction, "strumenti_vai_non_in_vocale")
            return
        # Il bot con «sposta membri» salta il limite di posti: il controllo di chi entra si fa qui, con i suoi permessi.
        motivo = puo_entrare_nel_vocale(canale.permissions_for(membro), canale)
        if motivo is not None:
            await self._dire(interaction, f"strumenti_{motivo}")
            return
        mio = canale.permissions_for(guild.me)
        if not (mio.connect and mio.move_members):
            await self._dire(interaction, "strumenti_bot_manca_permesso", permesso="move_members")
            return
        try:
            await membro.move_to(canale, reason="Si è spostato con /voice vai")
        except discord.HTTPException:
            await self._dire(interaction, "strumenti_non_riuscito")
            return
        await self._dire(interaction, "strumenti_vai_fatto", canale=canale.mention)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StrumentiServerCog(bot))
