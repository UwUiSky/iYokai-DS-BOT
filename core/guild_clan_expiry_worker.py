"""
core/guild_clan_expiry_worker.py
====================================
Servizio periodico che elimina automaticamente le gilde/clan la cui
finestra di 24h per colmare il deficit di creazione (SPEC.md §15.14,
CREATION_GRACE_HOURS in core/guild_clan_logic.py) è scaduta senza che
il deficit sia stato colmato — stesso pattern degli altri worker
periodici del progetto (tick con controllo orario, non serve più
frequente: la finestra è di ore, non minuti).

Elimina anche la categoria e i canali Discord creati alla fondazione
(se esistono ancora) PRIMA di eliminare il record dal database, così
non resta una categoria orfana senza nessun clan a cui appartiene.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.repositories.guild_clan_repo import guild_clan_repo

logger = logging.getLogger("iyokai.guild_clan_expiry_worker")

TICK_SECONDS = 3600


class GuildClanExpiryWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)

        for clan in await guild_clan_repo.get_unofficialized_expired(adesso):
            guild = bot.get_guild(clan.guild_id)
            if guild is not None and clan.category_id is not None:
                categoria = guild.get_channel(clan.category_id)
                if categoria is not None:
                    for canale in list(categoria.channels):
                        try:
                            await canale.delete(
                                reason=f"Gilda '{clan.tag}' scaduta senza colmare il deficit"
                            )
                        except discord.HTTPException:
                            logger.warning(
                                "Impossibile eliminare il canale %s della gilda scaduta %s.",
                                canale.id, clan.id,
                            )
                    try:
                        await categoria.delete(
                            reason=f"Gilda '{clan.tag}' scaduta senza colmare il deficit"
                        )
                    except discord.HTTPException:
                        logger.warning(
                            "Impossibile eliminare la categoria della gilda scaduta %s.", clan.id
                        )

            await guild_clan_repo.delete_clan(clan.id)
            logger.info(
                "Gilda '%s' (id %s) eliminata automaticamente: deficit di creazione non colmato entro la scadenza.",
                clan.tag, clan.id,
            )

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del guild clan expiry worker")

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info("Guild clan expiry worker avviato (controllo ogni %ds).", TICK_SECONDS)


guild_clan_expiry_worker = GuildClanExpiryWorker()
