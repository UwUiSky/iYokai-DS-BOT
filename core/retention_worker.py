"""
core/retention_worker.py
========================
Pulizia giornaliera (NF-04, GDPR-1/3, D6): i dati dei server in cui il bot non
c'è più da 90 giorni, e le righe vecchie delle tabelle che crescono.
Funzioni coperte: SPEC §19 (NF-04, #19, #75)
Dipende da: core/data_registry.py, core/repositories/guild_presence_repo.py

Un server si cancella a lotti di 5.000 righe, ognuno in una transazione corta che ricontrolla la presenza;
ban e kick di sicurezza restano (`conserva_se`). Se il bot rientra prima dei 90 giorni non si cancella niente.
Un server troppo grande riprende al giro dopo; l'ordine dei server è casuale, così uno che si inceppa non blocca gli altri.
Il lavoro regge una seconda esecuzione: cancellare due volte è innocuo.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone

import asyncpg
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.data_registry import GIORNI_DOPO_USCITA, REGISTRO, tabelle_con_scadenza
from core.forget_user_service import tabelle_esistenti, righe_toccate
from core.repositories.guild_presence_repo import guild_presence_repo
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.retention")

TICK_SECONDS = 24 * 3600


# Righe per istruzione: una DELETE enorme supera i 30 secondi del pool, blocca le altre scritture e,
# annullata, non lascia nessun progresso (il server resterebbe «da cancellare» per sempre).
LOTTO_RIGHE = 5000
# Tempo massimo per un server e per tutto il giro: oltre si smette e si riprende al giro dopo.
TEMPO_MASSIMO_SERVER = 120.0
TEMPO_MASSIMO_GIRO = 1800.0


class TempoFinito(Exception):
    """Il tempo per questo server è finito: i lotti già fatti restano, il resto al prossimo giro."""


def _controlla_tempo(scadenza: float | None) -> None:
    if scadenza is not None and time.monotonic() >= scadenza:
        raise TempoFinito()


async def _lotto_del_server(pool: asyncpg.Pool, guild_id: int, soglia: datetime, sql: str) -> int | None:
    """
    Un lotto in una transazione corta. La riga di presenza si blocca e si ricontrolla ogni volta:
    se il bot è rientrato nel frattempo si ferma (None), e un rientro aspetta al massimo un lotto.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            presenza = await conn.fetchrow(
                "SELECT left_at, purged_at FROM guild_presence WHERE guild_id = $1 FOR UPDATE", guild_id
            )
            if presenza is None or presenza["purged_at"] is not None or presenza["left_at"] is None \
                    or presenza["left_at"] >= soglia:
                return None  # rientrato (o già fatto): non si cancella niente
            return righe_toccate(await conn.execute(sql, guild_id))


async def purga_server(
    pool: asyncpg.Pool,
    guild_id: int,
    adesso: datetime | None = None,
    giorni: int = GIORNI_DOPO_USCITA,
    *,
    lotto: int = LOTTO_RIGHE,
    tempo_massimo: float | None = TEMPO_MASSIMO_SERVER,
) -> dict[str, int] | None:
    """
    Cancella i dati del server a lotti. Restituisce {tabella: righe cancellate}, o None se il server
    non è più da cancellare (rientrato o già fatto). Se scade `tempo_massimo` solleva `TempoFinito`:
    i lotti fatti restano e il lavoro riprende al giro dopo (il server è segnato fatto solo alla fine).
    """
    soglia = (adesso or datetime.now(timezone.utc)) - timedelta(days=giorni)
    scadenza = time.monotonic() + tempo_massimo if tempo_massimo is not None else None
    cancellate: dict[str, int] = {}
    async with pool.acquire() as conn:
        esistenti = await tabelle_esistenti(conn)
    for t in REGISTRO:
        sql = t.sql_cancella_server_a_lotti(lotto)
        if sql is None or t.nome not in esistenti:
            continue
        while True:
            _controlla_tempo(scadenza)
            n = await _lotto_del_server(pool, guild_id, soglia, sql)
            if n is None:
                return None
            if n:
                cancellate[t.nome] = cancellate.get(t.nome, 0) + n
            if n < lotto:
                break
    # Alla fine, in una transazione: ciò che deve sopravvivere (contatore dei casi) e il segno «fatto».
    async with pool.acquire() as conn:
        async with conn.transaction():
            presenza = await conn.fetchrow(
                "SELECT left_at, purged_at FROM guild_presence WHERE guild_id = $1 FOR UPDATE", guild_id
            )
            if presenza is None or presenza["purged_at"] is not None or presenza["left_at"] is None \
                    or presenza["left_at"] >= soglia:
                return None
            for t in REGISTRO:
                if t.dopo_purga_server and t.nome in esistenti:
                    await conn.execute(t.dopo_purga_server, guild_id)
            await guild_presence_repo.segna_cancellato(guild_id, conn=conn)
    _dimentica_memoria(guild_id)
    return cancellate


def _dimentica_memoria(guild_id: int) -> None:
    """Il server non esiste più per il database: via anche le copie in memoria."""
    from core.database import db
    from core.premium_cache import invalida_cache_premium

    db.dimentica_server(guild_id)
    invalida_cache_premium(guild_id)


async def pulisci_scaduti(
    pool: asyncpg.Pool, *, lotto: int = LOTTO_RIGHE, scadenza: float | None = None
) -> dict[str, int]:
    """
    Toglie le righe più vecchie della scadenza dichiarata nel registro, a lotti. Una tabella che sbaglia
    (database lento, tabella bloccata) si salta e si riprova al giro dopo: le altre vanno avanti.
    """
    tolte: dict[str, int] = {}
    async with pool.acquire() as conn:
        esistenti = await tabelle_esistenti(conn)
    for t in tabelle_con_scadenza():
        if t.nome not in esistenti:
            continue
        sql = t.sql_scaduti_a_lotti(lotto)
        try:
            while True:
                _controlla_tempo(scadenza)
                n = righe_toccate(await pool.execute(sql, t.scadenza.giorni))
                if n:
                    tolte[t.nome] = tolte.get(t.nome, 0) + n
                if n < lotto:
                    break
        except TempoFinito:
            logger.warning("Retention: tempo finito durante la pulizia di %s, riprendo al prossimo giro.", t.nome)
            break
        except Exception:
            logger.exception("Pulizia di %s fallita: passo alla prossima tabella.", t.nome)
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
    fine_giro = time.monotonic() + TEMPO_MASSIMO_GIRO
    da_fare = await guild_presence_repo.da_cancellare(adesso)
    random.shuffle(da_fare)  # un server che si inceppa non deve passare sempre per primo e togliere tempo agli altri
    for guild_id in da_fare:
        if guild_id in presenti:
            await guild_presence_repo.segna_entrato(guild_id)  # è tornato e nessuno lo aveva segnato
            continue
        if time.monotonic() >= fine_giro:
            logger.warning("Retention: tempo del giro finito, i server rimasti al prossimo giro.")
            break
        try:
            fatto = await purga_server(pool, guild_id, adesso)
            if fatto is not None:
                server[guild_id] = fatto
        except TempoFinito:
            logger.warning("Retention: server %s troppo grande per un giro, riprendo domani.", guild_id)
        except Exception:
            logger.exception("Cancellazione dei dati del server %s fallita.", guild_id)
    scaduti = await pulisci_scaduti(pool, scadenza=fine_giro)
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

        @giro_periodico(seconds=TICK_SECONDS)
        async def _loop():
            await self.tick(bot)  # un errore lo gestisce il GiroPeriodico: pausa crescente e nuovo tentativo

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Retention avviata (controllo ogni %ds).", TICK_SECONDS)


retention_worker = RetentionWorker()
