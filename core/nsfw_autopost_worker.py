"""
core/nsfw_autopost_worker.py
============================
Pubblicazione automatica dell'istanza NSFW: ogni 5 minuti prende i canali
scaduti, ricontrolla server attivo, canale vietato ai minori e tag permesso,
e pubblica un contenuto che passa i filtri. Dopo 5 errori di fila la
pubblicazione di quel canale si toglie da sola.
Funzioni coperte: SPEC §16.10 (NF-23)
Dipende da: core/nsfw_servizio.py
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import tasks

from core import nsfw_servizio as servizio
from core.bot_ready import attendi_bot_pronto
from core.repositories.nsfw_repo import NsfwAutopost, nsfw_repo

logger = logging.getLogger("iyokai.nsfw_autopost")

TICK_SECONDS = 5 * 60
MAX_PER_GIRO = 20
MAX_ERRORI = 5
PAUSA_TRA_INVII = 1.0


async def esegui_uno(
    bot: discord.Client, voce: NsfwAutopost, vista: Callable[[], discord.ui.View | None], adesso: datetime
) -> str:
    """Una pubblicazione. Restituisce l'esito ('pubblicato', 'tolto' o il motivo del rinvio)."""
    canale = bot.get_channel(voce.channel_id)
    esito = await servizio.scegli(voce.guild_id, voce.tag)
    if not isinstance(esito, str):
        esito = await servizio.pubblica(canale, esito, vista())
    if not isinstance(esito, str):
        await nsfw_repo.rimanda_autopost(
            voce.guild_id, voce.channel_id, adesso + timedelta(minutes=voce.intervallo_minuti), 0
        )
        return "pubblicato"
    errori = voce.errori + 1
    if errori >= MAX_ERRORI:
        await servizio.ferma_autopost(voce.guild_id, voce.channel_id)
        logger.info("Pubblicazione NSFW tolta (server %s, canale %s): %s", voce.guild_id, voce.channel_id, esito)
        return "tolto"
    await nsfw_repo.rimanda_autopost(
        voce.guild_id, voce.channel_id, adesso + timedelta(minutes=voce.intervallo_minuti), errori
    )
    return esito


class NsfwAutopostWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: discord.Client, vista: Callable[[], discord.ui.View | None]) -> None:
        for voce in await nsfw_repo.autopost_scaduti(MAX_PER_GIRO):
            try:
                await esegui_uno(bot, voce, vista, datetime.now(timezone.utc))
            except Exception:
                logger.exception("Errore nella pubblicazione NSFW (server %s)", voce.guild_id)
            await asyncio.sleep(PAUSA_TRA_INVII)

    def start(self, bot: discord.Client, vista: Callable[[], discord.ui.View | None]) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot, vista)
            except Exception:
                logger.exception("Errore nel giro delle pubblicazioni NSFW")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()


nsfw_autopost_worker = NsfwAutopostWorker()
