"""
cogs/music/eventi.py
====================
Ascolta il brano che inizia e finisce sui bot musicali: annuncio «ora in
riproduzione» nel canale scelto dal server e spegnimento del mescola fisso
quando la coda finisce.
Funzioni coperte: SPEC §9 (catalogo MUS-057, MUS-058, MUS-038)
Dipende da: core/music_announce_logic.py, core/music_settings_logic.py
"""

from __future__ import annotations

import asyncio
import logging
import random
import time

import discord
import wavelink
from discord.ext import commands

from core.database import db
from core.music_announce_logic import PausaAnnunci, embed_brano
from core.music_playlist_logic import brani_da_coda, brano_da_traccia
from core.music_settings_logic import load_music_settings, title_blocked, track_too_long
from core.repositories.music_playlist_repo import music_guild_playlist_repo, music_saved_queue_repo

logger = logging.getLogger("iyokai.music.eventi")

PAUSA_RISERVA = 20.0  # secondi tra due avvii della playlist di riserva (per server)
MAX_RISERVA = 50
ATTESA_SALVATAGGIO = 5.0


def coda_finita(player) -> bool:
    """Vero se dopo questo brano non ne resta nessuno (coda vuota e niente ripetizione)."""
    coda = getattr(player, "queue", None)
    if coda is None or not coda.is_empty:
        return False
    return getattr(coda, "mode", None) in (None, wavelink.QueueMode.normal)


class MusicEventiCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pausa = PausaAnnunci()
        self._ascoltatori: list[tuple[commands.Bot, object, object]] = []
        self._task: set[asyncio.Task] = set()
        self._ultima_riserva: dict[int, float] = {}
        self._salvataggi: dict[tuple[int, int], asyncio.Task] = {}

    def _in_background(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._task.add(task)
        task.add_done_callback(self._task.discard)

    async def cog_load(self) -> None:
        # Gli eventi wavelink arrivano al bot che ha il player: si ascolta su ogni worker.
        bot_con_player = [self.bot, *getattr(getattr(self.bot, "music_fleet", None), "worker_bots", [])]
        for worker in bot_con_player:
            worker.add_listener(self.su_inizio_brano, "on_wavelink_track_start")
            worker.add_listener(self.su_fine_brano, "on_wavelink_track_end")
            self._ascoltatori.append((worker, self.su_inizio_brano, self.su_fine_brano))

    async def cog_unload(self) -> None:
        for worker, inizio, fine in self._ascoltatori:
            worker.remove_listener(inizio, "on_wavelink_track_start")
            worker.remove_listener(fine, "on_wavelink_track_end")

    async def su_fine_brano(self, payload) -> None:
        """MUS-038: a coda finita il mescola fisso si spegne, anche se il bot resta connesso."""
        player = getattr(payload, "player", None)
        if player is not None and getattr(player, "mescola_fisso", False) and coda_finita(player):
            player.mescola_fisso = False
        if player is None or getattr(player, "is_radio", False) or getattr(player, "is_nonstop", False):
            return
        if getattr(payload, "reason", "") != "replaced":
            if coda_finita(player):
                self._in_background(self.riserva(player))  # MUS-040/041
            self.pianifica_salvataggio(player)  # MUS-042

    async def riserva(self, player, attesa: float = 0.5) -> bool:
        """MUS-040/041: a coda finita parte la playlist di riserva del server, se c'è qualcuno ad ascoltare."""
        guild = getattr(player, "guild", None)
        if guild is None:
            return False
        try:
            imp = await load_music_settings(db, guild.id)
            if not imp.fallback_playlist:
                return False
            umani = [m for m in getattr(getattr(player, "channel", None), "members", []) if not m.bot]
            adesso = time.monotonic()
            if not umani or adesso - self._ultima_riserva.get(guild.id, -1e9) < PAUSA_RISERVA:
                return False
            self._ultima_riserva[guild.id] = adesso  # prima di ogni await: niente ciclo stretto se i brani falliscono
            await asyncio.sleep(attesa)  # lascia finire l'avanzamento di wavelink
            if player.current is not None or not player.queue.is_empty:
                return False
            brani = await music_guild_playlist_repo.get(guild.id, imp.fallback_playlist)
            if not brani:
                return False
            from cogs.music.playlist import decodifica_brani  # evita un import circolare all'avvio

            lista = await decodifica_brani(player.node, imp.fallback_playlist, brani)
            if lista is None:
                return False
            tracce = [t for t in lista.tracks
                      if not title_blocked(t.title, imp) and not track_too_long(t.length, imp, t.is_stream)]
            random.shuffle(tracce)
            tracce = tracce[:MAX_RISERVA]
            if not tracce:
                return False
            player.queue.put(tracce[1:])
            await player.play(tracce[0])
            return True
        except Exception:
            logger.exception("Playlist di riserva non partita.")
            return False

    def pianifica_salvataggio(self, player) -> None:
        """MUS-042: salva la coda tra qualche secondo (un solo salvataggio per canale alla volta)."""
        guild, canale = getattr(player, "guild", None), getattr(player, "channel", None)
        if guild is None or canale is None or (guild.id, canale.id) in self._salvataggi:
            return
        task = asyncio.create_task(self._salva_coda(player, guild.id, canale.id))
        self._salvataggi[(guild.id, canale.id)] = task
        task.add_done_callback(lambda _t: self._salvataggi.pop((guild.id, canale.id), None))

    async def _salva_coda(self, player, guild_id: int, canale_id: int) -> None:
        await asyncio.sleep(ATTESA_SALVATAGGIO)
        try:
            if not (await load_music_settings(db, guild_id)).persist_queue:
                return
            brani, _fuori = brani_da_coda(player.current, player.queue)
            await music_saved_queue_repo.salva(guild_id, canale_id, brani)
        except Exception:
            logger.exception("Salvataggio della coda non riuscito.")

    async def su_inizio_brano(self, payload) -> None:
        """MUS-057/058: annuncia il brano che parte, se il server lo vuole."""
        player = getattr(payload, "player", None)
        guild = getattr(player, "guild", None)
        if guild is None or getattr(player, "is_radio", False) or getattr(player, "is_nonstop", False):
            return
        try:
            impostazioni = await load_music_settings(db, guild.id)
            if impostazioni.daily_playlist:  # MUS-045
                brano = brano_da_traccia(getattr(payload, "track", None))
                if brano is not None:
                    await music_guild_playlist_repo.aggiungi_del_giorno(guild.id, brano)
            if impostazioni.persist_queue:
                self.pianifica_salvataggio(player)
            if not impostazioni.announce or not impostazioni.announce_channel_id:
                return
            if getattr(getattr(player, "queue", None), "mode", None) == wavelink.QueueMode.loop:
                return  # brano ripetuto: un solo annuncio
            if not self.pausa.puo_annunciare(guild.id):
                return
            canale = self.bot.get_channel(impostazioni.announce_channel_id)
            if not isinstance(canale, discord.abc.Messageable) or getattr(canale, "guild", None) is None \
                    or canale.guild.id != guild.id:
                return
            traccia = getattr(payload, "track", None) or getattr(player, "current", None)
            if traccia is None:
                return
            await canale.send(
                embed=embed_brano(traccia), allowed_mentions=discord.AllowedMentions.none()
            )
        except (discord.HTTPException, discord.Forbidden):
            logger.info("Annuncio del brano non inviato nel server %s.", guild.id)
        except Exception:
            logger.exception("Annuncio del brano non riuscito.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicEventiCog(bot))
