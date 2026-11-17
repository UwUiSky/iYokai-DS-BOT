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

import logging

import discord
import wavelink
from discord.ext import commands

from core.database import db
from core.music_announce_logic import PausaAnnunci, embed_brano
from core.music_settings_logic import load_music_settings

logger = logging.getLogger("iyokai.music.eventi")


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

    async def su_inizio_brano(self, payload) -> None:
        """MUS-057/058: annuncia il brano che parte, se il server lo vuole."""
        player = getattr(payload, "player", None)
        guild = getattr(player, "guild", None)
        if guild is None or getattr(player, "is_radio", False) or getattr(player, "is_nonstop", False):
            return
        try:
            impostazioni = await load_music_settings(db, guild.id)
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
