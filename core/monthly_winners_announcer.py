"""
core/monthly_winners_announcer.py
=====================================
Servizio periodico dell'annuncio vincitori a fine mese (SPEC.md
§15.11) — stesso pattern di core/feed_watcher.py: tasks.loop avviato
una volta da main.py, non un Cog.

Tick ogni ora: basta per annunciare entro la prima ora del nuovo mese,
e non serve di più — non c'è nessun vantaggio reale nell'annunciare
alle 00:00:30 invece che alle 00:47. L'idempotenza vive nel database
(last_announced_period), quindi la frequenza del tick non influisce
sul numero di annunci: sempre uno per mese.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.monthly_winners_logic import (
    PODIUM_SIZE,
    build_announcement_text,
    previous_period_key,
    should_announce,
)
from core.repositories.leveling_repo import leveling_repo
from core.repositories.monthly_winners_repo import monthly_winners_repo

logger = logging.getLogger("iyokai.monthly_winners")

TICK_SECONDS = 3600


class MonthlyWinnersAnnouncer:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)
        periodo = previous_period_key(adesso)

        for config in await monthly_winners_repo.get_all_configs():
            if not should_announce(config.last_announced_period, adesso):
                continue

            guild = bot.get_guild(config.guild_id)
            canale = guild.get_channel(config.channel_id) if guild else None
            if not isinstance(canale, discord.TextChannel):
                # Canale sparito o bot uscito dal server: segniamo
                # comunque il periodo come coperto, altrimenti
                # riproveremmo (e logheremmo lo stesso avviso) ogni ora
                # per tutto il mese.
                logger.warning(
                    "Canale %s non raggiungibile per l'annuncio mensile del server %s.",
                    config.channel_id,
                    config.guild_id,
                )
                await monthly_winners_repo.mark_announced(config.guild_id, periodo)
                continue

            top_xp = await leveling_repo.top_xp_period(
                config.guild_id, limit=PODIUM_SIZE, period=periodo
            )
            top_coins = await leveling_repo.top_coins_period(
                config.guild_id, limit=PODIUM_SIZE, period=periodo
            )
            titolo, podio_xp, podio_coin = build_announcement_text(
                periodo,
                [(v.user_id, v.amount) for v in top_xp],
                [(v.user_id, v.amount) for v in top_coins],
            )

            embed = discord.Embed(title=titolo, color=discord.Color.gold())
            embed.add_field(name="✨ Più XP", value=podio_xp, inline=False)
            embed.add_field(name="💰 Più coin", value=podio_coin, inline=False)

            try:
                await canale.send(embed=embed)
            except discord.HTTPException:
                logger.warning(
                    "Impossibile pubblicare l'annuncio mensile nel server %s.", config.guild_id
                )
                # Non segniamo come annunciato: un errore transitorio
                # (rate limit, Discord momentaneamente giù) merita un
                # nuovo tentativo al tick successivo.
                continue

            await monthly_winners_repo.mark_announced(config.guild_id, periodo)

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick dell'annuncio mensile")

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info("Annuncio vincitori mensile avviato (controllo ogni %ds).", TICK_SECONDS)


monthly_winners_announcer = MonthlyWinnersAnnouncer()
