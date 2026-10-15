"""
cogs/music/request_channel.py
=============================
Canale delle richieste musicali: chi scrive un titolo, un link o allega un
file audio nel canale lo mette in coda; un messaggio "player" sempre
aggiornato ha i bottoni pausa, salta, stop, mescola, ripeti. Nessun ruolo
DJ e nessun voto (scelta dell'owner): vale la regola di tutti i comandi
musicali, cioè essere nel canale vocale del player.
Funzioni coperte: SPEC §23 (NF-19), M 8.19, catalogo MUS-009
Dipende da: cogs/music/player.py (MusicCog.accoda, ricerca del worker),
core/music_request_logic.py, core/repositories/music_request_repo.py.
"""

from __future__ import annotations

import asyncio
import logging

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.music_request_logic import (
    MODO_CODA,
    PAUSA_RICHIESTE,
    MODO_TRACCIA,
    PausaAggiornamenti,
    contenuto_player,
    modo_da_player,
    prossimo_modo_ripeti,
    query_da_messaggio,
    stato_da_player,
)
from core.music_sound_logic import PausaUtente
from core.repositories.music_request_repo import music_request_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.music.richieste")

SG_MUSICA = ("musica", "Musica: impostazioni del server")
MODULE_MUSIC = "music"
CANCELLA_RISPOSTE_DOPO = 15  # secondi: il canale resta pulito
_MODO_WAVELINK = {
    MODO_TRACCIA: wavelink.QueueMode.loop,
    MODO_CODA: wavelink.QueueMode.loop_all,
}


def embed_player(stato) -> discord.Embed:
    contenuto = contenuto_player(stato)
    embed = discord.Embed(
        title=contenuto["titolo"],
        description=contenuto["descrizione"],
        color=discord.Color.blurple(),
    )
    for nome, valore in contenuto["campi"]:
        embed.add_field(name=nome, value=valore, inline=nome != "In coda")
    embed.set_footer(text="Scrivi un titolo o un link in questo canale per metterlo in coda.")
    return embed


class PlayerRichiesteView(BaseView):
    """
    View persistente (timeout=None, custom_id fissi, add_view all'avvio):
    i bottoni di un messaggio player vecchio funzionano anche dopo un riavvio.
    """

    def __init__(self, cog: MusicRequestCog | None = None) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    async def _premi(self, interaction: discord.Interaction, azione: str) -> None:
        if self.cog is not None:
            await self.cog.premi(interaction, azione)

    @discord.ui.button(emoji="⏯️", label="Pausa", style=discord.ButtonStyle.secondary,
                       custom_id="iyokai_musreq_pausa", row=0)
    async def pausa(self, interaction: discord.Interaction, _b: discord.ui.Button) -> None:
        await self._premi(interaction, "pausa")

    @discord.ui.button(emoji="⏭️", label="Salta", style=discord.ButtonStyle.secondary,
                       custom_id="iyokai_musreq_salta", row=0)
    async def salta(self, interaction: discord.Interaction, _b: discord.ui.Button) -> None:
        await self._premi(interaction, "salta")

    @discord.ui.button(emoji="⏹️", label="Stop", style=discord.ButtonStyle.danger,
                       custom_id="iyokai_musreq_stop", row=0)
    async def stop_(self, interaction: discord.Interaction, _b: discord.ui.Button) -> None:
        await self._premi(interaction, "stop")

    @discord.ui.button(emoji="🔀", label="Mescola", style=discord.ButtonStyle.secondary,
                       custom_id="iyokai_musreq_mescola", row=0)
    async def mescola(self, interaction: discord.Interaction, _b: discord.ui.Button) -> None:
        await self._premi(interaction, "mescola")

    @discord.ui.button(emoji="🔁", label="Ripeti", style=discord.ButtonStyle.secondary,
                       custom_id="iyokai_musreq_ripeti", row=0)
    async def ripeti(self, interaction: discord.Interaction, _b: discord.ui.Button) -> None:
        await self._premi(interaction, "ripeti")


class MusicRequestCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.canali: dict[int, int] = {}  # server -> canale delle richieste
        self.pausa = PausaAggiornamenti()
        self.pausa_utenti = PausaUtente(pausa=PAUSA_RICHIESTE)
        self._in_attesa: dict[int, asyncio.Task] = {}
        self._task: set[asyncio.Task] = set()
        self._ascoltatori: list[tuple[commands.Bot, object]] = []

    async def cog_load(self) -> None:
        await super().cog_load()
        try:
            self.canali = {c.guild_id: c.channel_id for c in await music_request_repo.list_all()}
        except Exception:
            logger.exception("Lettura dei canali delle richieste non riuscita.")
        # Il brano cambia sul worker (i suoi eventi wavelink arrivano a lui):
        # si ascolta su ogni worker per aggiornare il messaggio player.
        for worker in getattr(getattr(self.bot, "music_fleet", None), "worker_bots", []):
            ascolto = self._su_evento_worker
            worker.add_listener(ascolto, "on_wavelink_track_start")
            worker.add_listener(ascolto, "on_wavelink_track_end")
            self._ascoltatori.append((worker, ascolto))

    async def cog_unload(self) -> None:
        await super().cog_unload()
        for worker, ascolto in self._ascoltatori:
            worker.remove_listener(ascolto, "on_wavelink_track_start")
            worker.remove_listener(ascolto, "on_wavelink_track_end")
        for task in list(self._in_attesa.values()) + list(self._task):
            task.cancel()

    def _in_background(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self._task.add(task)
        task.add_done_callback(self._task.discard)

    def _musica(self):
        return self.bot.get_cog("MusicCog")

    # ------------------------------------------------------------------
    # Comando di configurazione
    # ------------------------------------------------------------------
    @comando_di_gruppo(
        "admin",
        nome="canale-richieste",
        descrizione="Canale dove si scrive un titolo per metterlo in coda, con il player.",
        sottogruppo=SG_MUSICA,
    )
    @app_commands.describe(canale="Canale testuale delle richieste", disattiva="Togli il canale")
    async def canale_richieste(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel | None = None,
        disattiva: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        if disattiva:
            await interaction.response.defer(ephemeral=True)
            vecchio = await music_request_repo.remove(guild.id)
            self.canali.pop(guild.id, None)
            self.pausa.dimentica(guild.id)
            if vecchio is not None:
                await self._cancella_player(vecchio.channel_id, vecchio.message_id)
            await interaction.followup.send(
                "Canale delle richieste tolto." if vecchio else "Non c'era nessun canale delle richieste.",
                ephemeral=True,
            )
            return
        if canale is None:
            attuale = self.canali.get(guild.id)
            await interaction.response.send_message(
                f"Canale delle richieste: <#{attuale}>." if attuale
                else "Nessun canale delle richieste. Indica `canale` per sceglierne uno.",
                ephemeral=True,
            )
            return

        permessi = canale.permissions_for(guild.me)
        if not (permessi.view_channel and permessi.send_messages and permessi.embed_links):
            await interaction.response.send_message(
                f"Mi servono i permessi Vedi canale, Invia messaggi e Incorpora link in {canale.mention}.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            messaggio = await canale.send(embed=embed_player(None), view=PlayerRichiesteView(self))
        except discord.HTTPException:
            await interaction.followup.send("Non riesco a scrivere in quel canale.", ephemeral=True)
            return
        vecchio = await music_request_repo.get(guild.id)
        await music_request_repo.set_channel(guild.id, canale.id, messaggio.id, interaction.user.id)
        self.canali[guild.id] = canale.id
        if vecchio is not None and vecchio.message_id != messaggio.id:
            await self._cancella_player(vecchio.channel_id, vecchio.message_id)
        avviso = ""
        if not permessi.manage_messages:
            avviso = (
                "\nSenza il permesso Gestisci messaggi non posso cancellare le richieste "
                "scritte: il canale non resterà pulito."
            )
        await interaction.followup.send(
            f"✅ Canale delle richieste: {canale.mention}. Scrivete lì un titolo o un link.{avviso}",
            ephemeral=True,
        )

    async def _cancella_player(self, canale_id: int, messaggio_id: int | None) -> None:
        canale = self.bot.get_channel(canale_id)
        if canale is None or not messaggio_id:
            return
        try:
            await canale.get_partial_message(messaggio_id).delete()
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    # Messaggi scritti nel canale
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if self.canali.get(message.guild.id) != message.channel.id:
            return
        await self.gestisci_richiesta(message)

    async def gestisci_richiesta(self, message: discord.Message) -> None:
        query = query_da_messaggio(
            message.content, [(a.url, a.content_type) for a in message.attachments]
        )
        try:
            if query is None:
                return
            # Anti spam: le richieste troppo ravvicinate si cancellano e basta.
            if self.pausa_utenti.resta(message.guild.id, message.author.id) > 0:
                return
            self.pausa_utenti.segna(message.guild.id, message.author.id)
            canale = message.channel

            async def rispondi(testo: str) -> None:
                try:
                    await canale.send(
                        f"{message.author.mention} {testo}",
                        delete_after=CANCELLA_RISPOSTE_DOPO,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    pass

            if not await db.is_module_active_for_guild(message.guild.id, MODULE_MUSIC):
                await rispondi("Il modulo musica non è attivo su questo server.")
                return
            membro = message.author
            if not isinstance(membro, discord.Member) or membro.voice is None:
                await rispondi("Entra in un canale vocale, poi scrivi qui il titolo.")
                return
            musica = self._musica()
            if musica is None:
                return
            canale_vocale = await musica.accoda(message.guild, membro, query, rispondi)
            if canale_vocale:
                await music_request_repo.set_voice_channel(message.guild.id, canale_vocale)
                await self.aggiorna(message.guild.id)
        finally:
            try:
                await message.delete()
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # Bottoni del player
    # ------------------------------------------------------------------
    async def premi(self, interaction: discord.Interaction, azione: str) -> None:
        musica = self._musica()
        if musica is None or interaction.guild is None:
            await interaction.response.send_message("La musica non è disponibile ora.", ephemeral=True)
            return
        player = await musica._giocatore_attivo(interaction)
        if player is None:
            return
        await interaction.response.defer(ephemeral=True)
        testo = await esegui_azione(player, azione)
        await interaction.followup.send(testo, ephemeral=True)
        canale_vocale = getattr(getattr(player, "channel", None), "id", None)
        if canale_vocale:
            await music_request_repo.set_voice_channel(interaction.guild.id, canale_vocale)
        await self.aggiorna(interaction.guild.id)

    # ------------------------------------------------------------------
    # Aggiornamento del messaggio player (al massimo uno ogni 5 secondi)
    # ------------------------------------------------------------------
    async def _su_evento_worker(self, payload) -> None:
        guild = getattr(getattr(payload, "player", None), "guild", None)
        if guild is not None and guild.id in self.canali:
            self._in_background(self.aggiorna(guild.id))

    async def aggiorna(self, guild_id: int) -> None:
        attesa = self.pausa.attesa(guild_id)
        if attesa <= 0:
            # Segnato prima di ogni await: due eventi insieme (inizio e fine brano)
            # non passano entrambi e non mandano due messaggi player nuovi.
            self.pausa.segna(guild_id)
            await self.aggiorna_ora(guild_id)
            return
        if guild_id in self._in_attesa:
            return  # un aggiornamento è già in programma: mostrerà lo stato di quel momento

        async def _dopo() -> None:
            try:
                await asyncio.sleep(attesa)
                await self.aggiorna_ora(guild_id)
            finally:
                self._in_attesa.pop(guild_id, None)

        self._in_attesa[guild_id] = asyncio.create_task(_dopo())

    async def aggiorna_ora(self, guild_id: int) -> None:
        conf = await music_request_repo.get(guild_id)
        if conf is None:
            self.canali.pop(guild_id, None)
            return
        canale = self.bot.get_channel(conf.channel_id)
        if canale is None:
            return
        self.pausa.segna(guild_id)
        embed = embed_player(stato_da_player(await self._player(guild_id, conf.voice_channel_id)))
        try:
            if conf.message_id:
                await canale.get_partial_message(conf.message_id).edit(embed=embed)
                return
        except discord.NotFound:
            pass
        except discord.HTTPException:
            logger.warning("Aggiornamento del player nel server %s non riuscito.", guild_id)
            return
        try:  # messaggio cancellato a mano: se ne manda uno nuovo
            nuovo = await canale.send(embed=embed, view=PlayerRichiesteView(self))
            await music_request_repo.set_message(guild_id, nuovo.id)
        except discord.HTTPException:
            logger.warning("Nuovo messaggio player nel server %s non riuscito.", guild_id)

    async def _player(self, guild_id: int, canale_vocale: int | None):
        flotta = getattr(self.bot, "music_fleet", None)
        if flotta is None or not canale_vocale:
            return None
        assegnazione = await flotta.get_worker_for_channel(guild_id, canale_vocale)
        if assegnazione is None:
            return None
        worker_guild = assegnazione[1].get_guild(guild_id)
        return getattr(worker_guild, "voice_client", None)


async def esegui_azione(player, azione: str) -> str:
    """Un bottone del player sul player wavelink. Restituisce il testo per l'utente."""
    if azione == "pausa":
        nuova = not player.paused
        await player.pause(nuova)
        return "⏸️ Messo in pausa." if nuova else "▶️ Ripreso."
    if azione == "salta":
        if not player.playing:
            return "Non c'è nessun brano in riproduzione."
        await player.skip(force=True)
        return "⏭️ Brano saltato."
    if azione == "stop":
        player.queue.clear()
        await player.stop()
        return "⏹️ Riproduzione fermata, coda svuotata."
    if azione == "mescola":
        if player.queue.is_empty:
            return "La coda è vuota."
        player.queue.shuffle()
        return "🔀 Coda mescolata."
    if azione == "ripeti":
        nuovo = prossimo_modo_ripeti(modo_da_player(player.queue.mode))
        player.queue.mode = _MODO_WAVELINK.get(nuovo, wavelink.QueueMode.normal)
        return {
            MODO_TRACCIA: "🔂 Ripeto il brano.",
            MODO_CODA: "🔁 Ripeto la coda.",
        }.get(nuovo, "Ripetizione spenta.")
    return "Azione sconosciuta."


async def setup(bot: commands.Bot) -> None:
    cog = MusicRequestCog(bot)
    await bot.add_cog(cog)
    bot.add_view(PlayerRichiesteView(cog))
