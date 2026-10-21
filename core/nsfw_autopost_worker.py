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
from core.data_registry import GIORNI_DOPO_USCITA
from core.nsfw_filter_logic import canale_ammesso
from core.repositories.nsfw_repo import NsfwAutopost, nsfw_repo

logger = logging.getLogger("iyokai.nsfw_autopost")

TICK_SECONDS = 5 * 60
MAX_PER_GIRO = 20
MAX_ERRORI = 5
PAUSA_TRA_INVII = 1.0
# Pulizia D6 una volta ogni 6 ore (72 giri da 5 minuti), anche al primo giro.
GIRI_PER_PULIZIA = 72


async def esegui_uno(
    bot: discord.Client, voce: NsfwAutopost, vista: Callable[[], discord.ui.View | None], adesso: datetime
) -> str:
    """Una pubblicazione. Restituisce l'esito ('pubblicato', 'tolto' o il motivo del rinvio)."""
    if bot.get_guild(voce.guild_id) is None:
        # Il bot NSFW non è più nel server: niente tentativi, la pubblicazione si toglie subito.
        await servizio.ferma_autopost(voce.guild_id, voce.channel_id)
        return "tolto"
    canale = bot.get_channel(voce.channel_id)
    if not canale_ammesso(canale) or getattr(getattr(canale, "guild", None), "id", None) != voce.guild_id:
        esito = servizio.CANALE_NON_AMMESSO  # prima di chiedere alla fonte e di scaricare
    else:
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

    async def pulizia(self, bot: discord.Client) -> list[int]:
        """D6 per il solo bot NSFW: presenza dai server visti, dati cancellati 90 giorni dopo l'uscita."""
        ids = {g.id for g in bot.guilds}
        if ids:  # nessun server visibile = cache vuota, non "uscito da tutti"
            await nsfw_repo.sincronizza_presenza(ids)
        cancellati = await nsfw_repo.cancella_usciti(GIORNI_DOPO_USCITA)
        if cancellati:
            logger.info("Dati NSFW cancellati per %d server usciti da %d giorni.", len(cancellati), GIORNI_DOPO_USCITA)
        return cancellati

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
            if _loop.current_loop % GIRI_PER_PULIZIA == 0:
                try:
                    await self.pulizia(bot)
                except Exception:
                    logger.exception("Errore nella pulizia dei dati NSFW")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()


nsfw_autopost_worker = NsfwAutopostWorker()
