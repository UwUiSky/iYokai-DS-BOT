"""
core/retention_worker.py
========================
Pulizia giornaliera (NF-04, GDPR-1/3, D6): i dati dei server in cui il bot non
c'è più da 90 giorni, e le righe vecchie delle tabelle che crescono.
Funzioni coperte: SPEC §19 (NF-04, #19, #75)
Dipende da: core/data_registry.py, core/repositories/guild_presence_repo.py

Un server si cancella in una transazione sola; ban e kick di sicurezza restano
(`conserva_se`). Se il bot rientra prima dei 90 giorni non si cancella niente.
Il lavoro regge una seconda esecuzione: cancellare due volte è innocuo.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import asyncpg
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.data_registry import REGISTRO, tabelle_con_scadenza
from core.forget_user_service import tabelle_esistenti, _conta
from core.repositories.guild_presence_repo import guild_presence_repo

logger = logging.getLogger("iyokai.retention")

TICK_SECONDS = 24 * 3600


async def purga_server(pool: asyncpg.Pool, guild_id: int) -> dict[str, int]:
    """Cancella i dati del server (una transazione). Restituisce {tabella: righe cancellate}."""
    cancellate: dict[str, int] = {}
    async with pool.acquire() as conn:
        async with conn.transaction():
            esistenti = await tabelle_esistenti(conn)
            for t in REGISTRO:
                sql = t.sql_cancella_server()
                if sql is None or t.nome not in esistenti:
                    continue
                n = _conta(await conn.execute(sql, guild_id))
                if n:
                    cancellate[t.nome] = n
            await guild_presence_repo.segna_cancellato(guild_id, conn=conn)
    _dimentica_memoria(guild_id)
    return cancellate


def _dimentica_memoria(guild_id: int) -> None:
    """Il server non esiste più per il database: via anche le copie in memoria."""
    from core.database import db
    from core.premium_cache import invalida_cache_premium

    db._dimentica_server(guild_id)
    invalida_cache_premium(guild_id)


async def pulisci_scaduti(pool: asyncpg.Pool) -> dict[str, int]:
    """Toglie le righe più vecchie della scadenza dichiarata nel registro."""
    tolte: dict[str, int] = {}
    async with pool.acquire() as conn:
        esistenti = await tabelle_esistenti(conn)
    for t in tabelle_con_scadenza():
        if t.nome not in esistenti:
            continue
        try:
            n = _conta(await pool.execute(t.sql_scaduti(), t.scadenza.giorni))
        except asyncpg.PostgresError:
            logger.exception("Pulizia di %s fallita: passo alla prossima tabella.", t.nome)
            continue
        if n:
            tolte[t.nome] = n
    return tolte


async def giro(
    pool: asyncpg.Pool,
    guild_ids_presenti: set[int] | None = None,
    adesso: datetime | None = None,
) -> dict:
    """
    Un giro completo. `guild_ids_presenti` sono i server in cui il bot è adesso:
    non si toccano mai, qualunque cosa dica la tabella.
    """
    adesso = adesso or datetime.now(timezone.utc)
    presenti = guild_ids_presenti or set()
    server: dict[int, dict[str, int]] = {}
    for guild_id in await guild_presence_repo.da_cancellare(adesso):
        if guild_id in presenti:
            await guild_presence_repo.segna_entrato(guild_id)  # è tornato e nessuno lo aveva segnato
            continue
        try:
            server[guild_id] = await purga_server(pool, guild_id)
        except asyncpg.PostgresError:
            logger.exception("Cancellazione dei dati del server %s fallita.", guild_id)
    scaduti = await pulisci_scaduti(pool)
    if server or scaduti:
        logger.info(
            "Retention: %d server cancellati, %d righe scadute tolte.",
            len(server),
            sum(scaduti.values()),
        )
    return {"server": server, "scaduti": scaduti}


class RetentionWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot) -> dict:
        from core.database import db

        ids = {g.id for g in bot.guilds}
        if ids:
            usciti = await guild_presence_repo.sincronizza(ids)
            if usciti:
                logger.info("Presenza: %d server non più visibili, partono i 90 giorni.", usciti)
        else:
            logger.warning("Nessun server visibile: salto la sincronizzazione della presenza.")
        return await giro(db.pool, ids)

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel giro della retention")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Retention avviata (controllo ogni %ds).", TICK_SECONDS)


retention_worker = RetentionWorker()
