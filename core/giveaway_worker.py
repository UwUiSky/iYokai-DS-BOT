"""
core/giveaway_worker.py
===========================
Servizio periodico che estrae i vincitori dei giveaway scaduti
(SPEC.md §15.5) — stesso pattern di core/feed_watcher.py e core/
monthly_winners_announcer.py: tasks.loop avviato una volta da
main.py, non un Cog.

Tick ogni 30 secondi: abbastanza reattivo perché un giveaway di
"1 minuto" (durata minima) non resti scaduto per troppo a lungo
prima dell'estrazione, senza sovraccaricare inutilmente per giveaway
che durano ore o giorni.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.giveaway_logic import pick_winners
from core.repositories.giveaway_repo import giveaway_repo

logger = logging.getLogger("iyokai.giveaway_worker")

TICK_SECONDS = 30


class GiveawayWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)

        for giveaway in await giveaway_repo.get_due_giveaways(adesso):
            # Segnato concluso SUBITO, prima di qualunque operazione
            # che potrebbe fallire (canale sparito, ecc.) — un
            # giveaway scaduto non deve restare "dovuto" per sempre
            # e essere ritentato ad ogni tick.
            await giveaway_repo.mark_ended(giveaway.id)

            partecipanti = await giveaway_repo.get_entries(giveaway.id)
            vincitori = pick_winners(partecipanti, giveaway.winners_count, random.Random())

            guild = bot.get_guild(giveaway.guild_id)
            canale = guild.get_channel(giveaway.channel_id) if guild else None
            if not isinstance(canale, discord.TextChannel):
                logger.warning(
                    "Canale %s non raggiungibile per la fine del giveaway %s.",
                    giveaway.channel_id,
                    giveaway.id,
                )
                continue

            if not vincitori:
                testo = f"🎉 Il giveaway per **{giveaway.prize}** è terminato, ma nessuno ha partecipato."
            else:
                menzioni = ", ".join(f"<@{uid}>" for uid in vincitori)
                testo = f"🎉 Congratulazioni {menzioni}! Avete vinto **{giveaway.prize}**!"

            try:
                await canale.send(testo)
            except discord.HTTPException:
                logger.warning(
                    "Impossibile annunciare la fine del giveaway %s nel canale %s.",
                    giveaway.id,
                    giveaway.channel_id,
                )

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del giveaway worker")

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info("Giveaway worker avviato (controllo ogni %ds).", TICK_SECONDS)


giveaway_worker = GiveawayWorker()
