"""
core/birthday_worker.py
=======================
Auguri giornalieri e ruolo a tempo (NF-26). Il giro gira ogni mezz'ora; per ogni server con
il canale degli auguri, chi festeggia oggi (UTC) e non ha ancora ricevuto gli auguri
quest'anno viene "prenotato" nel database (due giri insieme non mandano due volte) e
festeggiato con un messaggio solo per tutti. Il ruolo dura 24 ore e lo toglie lo scheduler.
Funzioni coperte: SPEC §23 (NF-26)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord

from core.birthday_logic import dividi_auguri
from core.guild_iteration import for_each_guild_safely
from core.role_safety import motivo_ruolo_automatico_non_assegnabile

logger = logging.getLogger("iyokai.birthdays")

BIRTHDAY_ROLE_ACTION_TYPE = "birthday_role_remove"
MODULE_BIRTHDAYS = "birthdays"
DURATA_RUOLO = timedelta(hours=24)


class BirthdayWorker:
    def __init__(self, repo, scheduler, db=None) -> None:
        self._repo = repo
        self._scheduler = scheduler
        if db is None:
            from core.database import db as db_globale

            db = db_globale
        self._db = db

    async def tick(self, bot, ora: datetime | None = None) -> None:
        ora = ora or datetime.now(timezone.utc)
        configs = await self._repo.list_active_configs()

        async def per_server(config) -> None:
            await self._server(bot, config, ora)

        class _Elemento:
            def __init__(self, c):
                self.id = c.guild_id
                self.config = c

        async def operazione(e) -> None:
            await per_server(e.config)

        await for_each_guild_safely([_Elemento(c) for c in configs], operazione, nome_worker="birthday_worker")

    async def _server(self, bot, config, ora: datetime) -> None:
        guild = bot.get_guild(config.guild_id)
        if guild is None or not await self._db.is_module_active_for_guild(config.guild_id, MODULE_BIRTHDAYS):
            return
        canale = guild.get_channel(config.channel_id)
        if not isinstance(canale, discord.TextChannel):
            return
        utenti = await self._repo.claim_due(config.guild_id, ora.date())
        if not utenti:
            return
        membri = [m for m in (guild.get_member(u) for u in utenti) if m is not None and not m.bot]
        if not membri:
            return
        permessi = discord.AllowedMentions(users=True, roles=config.ping_ruoli, everyone=False)
        try:
            for testo in dividi_auguri(config.message, [m.mention for m in membri]):
                await canale.send(testo, allowed_mentions=permessi)
        except discord.HTTPException as errore:
            # Gli auguri non sono (tutti) partiti: si riprova al giro dopo, per tutta la giornata.
            logger.warning("Auguri non inviati nel server %s: %s", config.guild_id, errore)
            await self._repo.release_claim(config.guild_id, utenti, ora.year)
            return
        if config.role_id is not None:
            await self._ruolo(guild, config.role_id, membri, ora)

    async def _ruolo(self, guild, role_id: int, membri, ora: datetime) -> None:
        motivo = motivo_ruolo_automatico_non_assegnabile(guild, role_id)
        if motivo is not None:
            logger.warning("Ruolo del compleanno non assegnabile nel server %s: %s", guild.id, motivo)
            return
        ruolo = guild.get_role(role_id)
        for membro in membri:
            try:
                await membro.add_roles(ruolo, reason="Compleanno")
            except discord.HTTPException:
                logger.warning("Ruolo del compleanno non dato a %s nel server %s", membro.id, guild.id)
                continue
            await self._scheduler.schedule(
                guild.id, membro.id, BIRTHDAY_ROLE_ACTION_TYPE, ora + DURATA_RUOLO, {"role_id": role_id}
            )
