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
Una gilda con il debito già coperto non si cancella: diventa ufficiale.
Funzioni coperte: REVIEW.md LC-8 (errori isolati per server nel giro),
BUG-15.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.guild_clan_logic import is_creation_deficit_covered
from core.guild_clan_role_service import clear_clan_officers_presence
from core.guild_iteration import for_each_guild_safely
from core.repositories.guild_clan_repo import guild_clan_repo

logger = logging.getLogger("iyokai.guild_clan_expiry_worker")

TICK_SECONDS = 3600


class GuildClanExpiryWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)

        async def _per_clan(clan) -> None:
            # BUG-15: debito già coperto (per esempio con un
            # trasferimento fatto prima che diventasse ufficiale da
            # solo): la gilda si rende ufficiale, non si cancella.
            if is_creation_deficit_covered(clan.treasury_balance):
                await guild_clan_repo.set_officialized(clan.id)
                logger.info(
                    "Gilda '%s' (id %s) resa ufficiale: il debito di creazione era già coperto.",
                    clan.tag, clan.id,
                )
                return

            guild = bot.get_guild(clan.guild_id)
            if guild is not None:
                # Gli ufficiali non devono restare con "Capo Clan" o
                # "Admin Clan" di una gilda che non esiste più.
                await clear_clan_officers_presence(
                    guild, None, await guild_clan_repo.list_members(clan.id)
                )
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

        # LC-8: una gilda problematica non blocca le altre.
        await for_each_guild_safely(
            await guild_clan_repo.get_unofficialized_expired(adesso),
            _per_clan,
            nome_worker="Scadenza gilde",
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
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Guild clan expiry worker avviato (controllo ogni %ds).", TICK_SECONDS)


guild_clan_expiry_worker = GuildClanExpiryWorker()
