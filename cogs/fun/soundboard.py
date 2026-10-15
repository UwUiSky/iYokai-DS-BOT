"""
cogs/fun/soundboard.py
======================
Effetti sonori in vocale: un suono della soundboard (del server o
predefinito di Discord) suonato da un bot musicale nel canale di chi lo
chiede. Se il canale ha già un bot musicale si usa quello (la musica non
si ferma); se no entra il primo libero, suona e poi esce. Pausa per utente.
Il comando sta nel gruppo music (il gruppo fun ha già 25 figli).
Funzioni coperte: SPEC §23 (NF-35)
Dipende da: cogs/music/player.py (worker, nodo, ingresso nel canale),
core/music_sound_logic.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.music_settings_logic import channel_not_allowed, load_music_settings
from core.music_sound_logic import ATTESA_USCITA, PausaUtente, Suono, scelte, trova

logger = logging.getLogger("iyokai.music.suoni")

MSG_NESSUN_NODO = "Nessun nodo audio è collegato per il music bot libero. Riprova tra poco."
RIPRISTINA_SORDO_DOPO = 6.0  # secondi


class SoundboardCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pausa = PausaUtente()
        self._predefiniti: list = []
        self._task: set[asyncio.Task] = set()
        # Uscita programmata del bot entrato solo per i suoni, per (server, canale).
        self._uscite: dict[tuple[int, int], asyncio.Task] = {}

    async def cog_unload(self) -> None:
        await super().cog_unload()
        for task in list(self._task):
            task.cancel()

    def _in_background(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self._task.add(task)
        task.add_done_callback(self._task.discard)
        return task

    def _programma_uscita(self, musica, flotta, worker_guild, guild_id: int, canale_id: int) -> None:
        """
        Un suono nuovo nel canale del bot temporaneo sposta in avanti la sua
        uscita: quella vecchia non lo taglia a metà.
        """
        chiave = (guild_id, canale_id)
        vecchia = self._uscite.pop(chiave, None)
        if vecchia is not None:
            vecchia.cancel()
        task = self._in_background(
            _esci_se_inattivo(
                flotta, worker_guild, guild_id, canale_id, lock=musica._lock_canale(guild_id, canale_id)
            )
        )
        self._uscite[chiave] = task

        def _togli(t: asyncio.Task) -> None:
            if self._uscite.get(chiave) is t:
                self._uscite.pop(chiave, None)

        task.add_done_callback(_togli)

    async def _suoni(self, guild: discord.Guild) -> dict[str, tuple[Suono, object]]:
        """Valore -> (Suono, oggetto discord.py). I predefiniti si leggono una volta sola."""
        if not self._predefiniti:
            try:
                self._predefiniti = list(await self.bot.fetch_soundboard_default_sounds())
            except discord.HTTPException:
                logger.warning("Suoni predefiniti di Discord non letti.")
        tutti: dict[str, tuple[Suono, object]] = {}
        for s in getattr(guild, "soundboard_sounds", []) or []:
            if getattr(s, "available", True):
                suono = Suono(s.id, s.name, True, str(s.emoji) if s.emoji else None)
                tutti[suono.valore] = (suono, s)
        for s in self._predefiniti:
            suono = Suono(s.id, s.name, False, str(s.emoji) if getattr(s, "emoji", None) else None)
            tutti[suono.valore] = (suono, s)
        return tutti

    async def _nomi(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        suoni = [s for s, _ in (await self._suoni(interaction.guild)).values()]
        return [app_commands.Choice(name=e, value=v) for e, v in scelte(suoni, current)]

    @comando_di_gruppo("music", nome="suono", descrizione="Fa partire un effetto sonoro nel tuo canale vocale.")
    @app_commands.describe(nome="Il suono: della soundboard del server o di Discord")
    @app_commands.autocomplete(nome=_nomi)
    async def suono(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 100]) -> None:
        musica = self.bot.get_cog("MusicCog")
        if musica is None:
            await interaction.response.send_message("La musica non è disponibile ora.", ephemeral=True)
            return
        if not await musica._controlli_base(interaction):
            return
        guild = interaction.guild
        resta = self.pausa.resta(guild.id, interaction.user.id)
        if resta > 0:
            await interaction.response.send_message(
                f"Aspetta ancora {int(resta) + 1} secondi prima del prossimo suono.", ephemeral=True
            )
            return
        canale_id = interaction.user.voice.channel.id
        rifiuto = channel_not_allowed(canale_id, await load_music_settings(db, guild.id))
        if rifiuto:
            await interaction.response.send_message(rifiuto, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        disponibili = await self._suoni(guild)
        trovato = trova([s for s, _ in disponibili.values()], nome)
        if trovato is None:
            await interaction.followup.send("Suono non trovato: sceglilo dall'elenco.", ephemeral=True)
            return
        oggetto = disponibili[trovato.valore][1]
        self.pausa.segna(guild.id, interaction.user.id)
        testo = await self.suona(musica, interaction, canale_id, oggetto)
        await interaction.followup.send(testo.replace("{nome}", trovato.nome), ephemeral=True)

    async def suona(self, musica, interaction: discord.Interaction, canale_id: int, oggetto) -> str:
        """Manda il suono dal bot musicale del canale (o dal primo libero). Restituisce il testo."""
        guild_id = interaction.guild.id
        flotta = self.bot.music_fleet
        worker_bot, worker_guild, errore = await musica._get_worker(
            guild_id, auto_assign=True, interaction=interaction
        )
        if errore:
            return errore
        async with musica._lock_canale(guild_id, canale_id):
            player = worker_guild.voice_client
            temporaneo = False
            if player is None:
                nodo = _nodo_del_bot(self.bot, worker_bot)
                canale_worker = worker_guild.get_channel(canale_id)
                if nodo is None or canale_worker is None:
                    await musica._rilascia_se_libero(worker_guild, guild_id, canale_id)
                    return MSG_NESSUN_NODO if nodo is None else "Il music bot non vede il tuo canale."
                # Un bot "sordo" non può mandare suoni: qui si entra con l'audio acceso.
                player, errore = await musica._entra_in_canale(canale_worker, nodo, sordo=False)
                if errore:
                    await musica._rilascia_se_libero(worker_guild, guild_id, canale_id)
                    return errore
                temporaneo = True
            canale = player.channel
            era_sordo = bool(getattr(getattr(worker_guild.me, "voice", None), "self_deaf", False))
            try:
                if era_sordo:
                    await worker_guild.change_voice_state(channel=canale, self_deaf=False)
                await canale.send_sound(oggetto)
            except discord.Forbidden:
                return "Il music bot non ha il permesso di usare la soundboard in questo canale."
            except discord.HTTPException:
                logger.warning("Invio del suono non riuscito nel server %s.", guild_id)
                return "Non sono riuscito a far partire il suono. Riprova tra poco."
            finally:
                if era_sordo:
                    self._in_background(_torna_sordo(worker_guild, RIPRISTINA_SORDO_DOPO))
                if temporaneo or (guild_id, canale_id) in self._uscite:
                    self._programma_uscita(musica, flotta, worker_guild, guild_id, canale_id)
        return "🔊 Suono **{nome}** partito."


def _nodo_del_bot(bot, worker_bot):
    from cogs.music.player import chiave_del_bot

    gestore = getattr(bot, "music_nodes", None)
    return gestore.node_for(chiave_del_bot(worker_bot)) if gestore else None


async def _torna_sordo(worker_guild, attesa: float) -> None:
    await asyncio.sleep(attesa)
    voce = getattr(worker_guild.me, "voice", None)
    if voce is not None and voce.channel is not None:
        try:
            await worker_guild.change_voice_state(channel=voce.channel, self_deaf=True)
        except discord.HTTPException:
            pass


async def _esci_se_inattivo(flotta, worker_guild, guild_id: int, canale_id: int,
                            attesa: float = ATTESA_USCITA, lock: asyncio.Lock | None = None) -> None:
    """
    Il bot entrato solo per il suono esce, a meno che nel frattempo qualcuno
    abbia messo musica. Il controllo si fa con il lock del canale di
    MusicCog: un /music play a metà (ricerca in corso) non trova il player
    scollegato sotto di sé.
    """
    await asyncio.sleep(attesa)
    async with lock if lock is not None else contextlib.nullcontext():
        player = worker_guild.voice_client
        if player is None:
            return
        if getattr(player, "playing", False) or not getattr(player.queue, "is_empty", True):
            return
        try:
            await player.disconnect()
        finally:
            await flotta.release_session(guild_id, canale_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SoundboardCog(bot))
