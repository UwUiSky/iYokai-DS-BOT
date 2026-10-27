"""
core/counter_worker.py
======================
Aggiorna i nomi dei canali contatore (NF-16). Un giro ogni 10 minuti (LIM-3: Discord
permette 2 rinomine ogni 10 minuti per canale): un canale si rinomina solo se il numero
è cambiato, e se Discord dice di aspettare si riprova al giro dopo. Un errore su un
server non ferma gli altri.
Funzioni coperte: SPEC §23 (NF-16)
"""

from __future__ import annotations

import logging

import discord

from core.channel_rename import RenameRateLimited, rename_channel
from core.counter_logic import Istantanea, nome_canale, valore_del_contatore
from core.guild_iteration import for_each_guild_safely

logger = logging.getLogger("iyokai.counters")


class _Gruppo:
    """Un server con i suoi contatori: serve a for_each_guild_safely (nome nei log)."""

    def __init__(self, guild_id: int, contatori: list) -> None:
        self.id = guild_id
        self.contatori = contatori


class CounterWorker:
    def __init__(self, repo, rename=rename_channel, db=None, conta_ticket=None) -> None:
        self._repo = repo
        self._rename = rename
        if conta_ticket is None:
            from core.repositories.ticket_repo import ticket_repo

            conta_ticket = lambda guild_id: ticket_repo.count_open_tickets(guild_id)  # noqa: E731
        self._conta_ticket = conta_ticket
        if db is None:
            from core.database import db as db_globale

            db = db_globale
        self._db = db

    async def tick(self, bot) -> None:
        tutti = await self._repo.list_all()
        gruppi: dict[int, list] = {}
        for contatore in tutti:
            gruppi.setdefault(contatore.guild_id, []).append(contatore)
        elementi = [_Gruppo(g, c) for g, c in gruppi.items()]

        async def per_server(gruppo: _Gruppo) -> None:
            await self._aggiorna_server(bot, gruppo)

        await for_each_guild_safely(elementi, per_server, nome_worker="counter_worker")

    async def _aggiorna_server(self, bot, gruppo: _Gruppo) -> None:
        guild = bot.get_guild(gruppo.id)
        if guild is None or not await self._db.is_module_active_for_guild(gruppo.id, "counters"):
            return
        online = None
        if any(c.kind == "online" for c in gruppo.contatori):
            # Una sola richiesta per server, qualunque sia il numero di contatori "online".
            try:
                con_conteggi = await bot.fetch_guild(gruppo.id, with_counts=True)
                online = con_conteggi.approximate_presence_count
            except discord.HTTPException:
                logger.warning("Contatori: conteggio online non letto nel server %s", gruppo.id)
        ticket = None
        if any(c.kind == "tickets" for c in gruppo.contatori):
            ticket = await self._conta_ticket(gruppo.id)
        snap = Istantanea(
            member_count=guild.member_count or 0,
            online_count=online,
            boost_count=guild.premium_subscription_count or 0,
            ticket_aperti=ticket,
            ruoli=len(guild.roles),
            canali=len(guild.channels),
            emoji=len(guild.emojis),
        )
        for contatore in gruppo.contatori:
            await self._aggiorna_contatore(guild, contatore, snap)

    async def _aggiorna_contatore(self, guild, contatore, snap: Istantanea) -> None:
        canale = guild.get_channel(contatore.channel_id)
        if canale is None:
            await self._repo.delete_by_channel(contatore.channel_id)  # cancellato: il contatore non serve più
            return
        valore = valore_del_contatore(contatore.kind, snap)
        if valore is None or valore == contatore.last_value:
            return
        nome = nome_canale(contatore.label, valore, contatore.target)
        try:
            if canale.name != nome:
                await self._rename(canale, nome, reason="Contatore")
        except RenameRateLimited:
            return  # al prossimo giro
        except discord.NotFound:
            await self._repo.delete_by_channel(contatore.channel_id)
            return
        except discord.HTTPException as errore:
            logger.warning("Contatore %s: rinomina non riuscita nel server %s: %s", contatore.id, guild.id, errore)
            return
        await self._repo.set_last_value(contatore.id, valore)
