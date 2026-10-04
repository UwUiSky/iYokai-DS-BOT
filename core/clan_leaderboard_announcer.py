"""
core/clan_leaderboard_announcer.py
======================================
Servizio periodico dell'annuncio della top 3 gilde a fine mese in
"bacheca clan" (SPEC.md §15.10 — richiesta esplicita dell'utente:
"ogni mese, il bot pubblica in bacheca clan la top 3"). Stesso
identico pattern di core/monthly_winners_announcer.py (§15.11,
annuncio vincitori personale): tasks.loop avviato una volta da
main.py, non un Cog, tick ogni ora — l'idempotenza vive nel database
(last_announced_period), quindi la frequenza del tick non influisce
sul numero di annunci: sempre uno per mese.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.clan_leaderboard_logic import (
    PODIUM_SIZE,
    build_clan_announcement_text,
    previous_period_key,
    should_announce,
)
from core.repositories.clan_leaderboard_config_repo import clan_leaderboard_config_repo
from core.repositories.guild_clan_repo import guild_clan_repo

logger = logging.getLogger("iyokai.clan_leaderboard")

TICK_SECONDS = 3600


class ClanLeaderboardAnnouncer:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)
        periodo = previous_period_key(adesso)

        for config in await clan_leaderboard_config_repo.get_all_configs():
            if not should_announce(config.last_announced_period, adesso):
                continue

            guild = bot.get_guild(config.guild_id)
            canale = guild.get_channel(config.channel_id) if guild else None
            if not isinstance(canale, discord.TextChannel):
                # Canale sparito o bot uscito dal server: segniamo
                # comunque il periodo come coperto, altrimenti
                # riproveremmo (e logheremmo lo stesso avviso) ogni ora
                # per tutto il mese — stessa scelta di
                # monthly_winners_announcer.
                logger.warning(
                    "Canale %s non raggiungibile per la bacheca clan del server %s.",
                    config.channel_id,
                    config.guild_id,
                )
                await clan_leaderboard_config_repo.mark_announced(config.guild_id, periodo)
                continue

            top_clan = await guild_clan_repo.get_monthly_clan_leaderboard(
                config.guild_id, period=periodo, limit=PODIUM_SIZE
            )
            titolo, podio = build_clan_announcement_text(
                periodo,
                [(clan.tag, clan.name, xp) for clan, xp in top_clan],
            )

            embed = discord.Embed(title=titolo, description=podio, color=discord.Color.gold())

            try:
                await canale.send(embed=embed)
            except discord.HTTPException:
                logger.warning(
                    "Impossibile pubblicare la bacheca clan nel server %s.", config.guild_id
                )
                # Non segniamo come annunciato: un errore transitorio
                # (rate limit, Discord momentaneamente giù) merita un
                # nuovo tentativo al tick successivo.
                continue

            await clan_leaderboard_config_repo.mark_announced(config.guild_id, periodo)

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick della bacheca clan")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Bacheca clan mensile avviata (controllo ogni %ds).", TICK_SECONDS)


clan_leaderboard_announcer = ClanLeaderboardAnnouncer()
