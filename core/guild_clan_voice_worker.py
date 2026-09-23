"""
core/guild_clan_voice_worker.py
===================================
Servizio periodico che applica i tick vocali dei membri di clan
(SPEC.md §15.14) — stesso pattern di feed_watcher.py/leveling
(_process_guild_voice_xp): tasks.loop avviato una volta da main.py,
non un Cog.

Tick al MINUTO (confermato esplicitamente dall'utente — non ai 2
minuti, quella finestra è solo manutenzione/reset giornaliero
23:59->00:01, non un tick vero). Iterando i canali vocali live dei
server, non c'è bisogno di on_voice_state_update per sapere chi è
dove in questo istante — lo stato PRECEDENTE (canale, decadimento,
tetto) vive nel database tramite core/repositories/clan_voice_
activity_repo.py, già committato.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from discord.ext import commands, tasks

from core.repositories.clan_voice_activity_repo import clan_voice_activity_repo
from core.repositories.guild_clan_repo import guild_clan_repo

logger = logging.getLogger("iyokai.guild_clan_voice_worker")

TICK_SECONDS = 60


class GuildClanVoiceWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)
        oggi: date = adesso.date()

        trovati_in_vocale: set[tuple[int, int]] = set()

        for guild in bot.guilds:
            for canale in guild.voice_channels:
                for membro in canale.members:
                    if membro.bot:
                        continue

                    clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, membro.id)
                    if clan is None or not clan.officialized:
                        # Non ufficializzato = ancora in prova, non
                        # matura ancora XP/coin di gilda: l'utente
                        # deve prima colmare il deficit di creazione.
                        continue

                    trovati_in_vocale.add((clan.id, membro.id))

                    xp, coin = await clan_voice_activity_repo.apply_tick(
                        clan.id, membro.id, canale.id, oggi
                    )
                    if xp > 0:
                        await guild_clan_repo.add_xp(clan.id, xp)
                    if coin > 0:
                        await guild_clan_repo.apply_treasury_delta(
                            clan.id, coin, reason="voice_tick"
                        )

        # Chi risultava "in vocale" al tick precedente ma non è stato
        # ritrovato in NESSUN canale in questo giro è uscito dal
        # vocale nel frattempo — va ripulito, altrimenti al rientro
        # (magari ore dopo) verrebbe trattato come se non avesse mai
        # smesso, con un decadimento già a metà strada invece che da
        # zero.
        for clan_id, user_id in await clan_voice_activity_repo.get_tracked_as_in_voice():
            if (clan_id, user_id) not in trovati_in_vocale:
                await clan_voice_activity_repo.clear_activity(clan_id, user_id)

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del guild clan voice worker")

        @_loop.before_loop
        async def _before():
            await bot.wait_until_ready()

        self._loop_task = _loop
        _loop.start()
        logger.info("Guild clan voice worker avviato (controllo ogni %ds).", TICK_SECONDS)


guild_clan_voice_worker = GuildClanVoiceWorker()
