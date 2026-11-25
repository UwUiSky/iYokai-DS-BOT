"""
tests/test_pool_db.py
=====================
Il pool con attesa massima e corsia per gli eventi; controlli dei comandi che non superano i 3 secondi;
cache delle sospensioni dal gioco. PostgreSQL vero.
Funzioni coperte: consiglio 25/11/2026, critico 9 (blocco C)
"""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import blacklist_tree, economia_sospensioni as es, pool_db
from core.pool_db import CORSIA_EVENTI, PoolConCorsie, connessioni_per_eventi, corsia_db


async def _pool(max_size=3):
    return await PoolConCorsie(
        os.environ["DATABASE_URL"], min_size=1, max_size=max_size, max_queries=50000,
        max_inactive_connection_lifetime=300.0, loop=None,
        connection_class=pool_db.asyncpg.Connection, record_class=pool_db.asyncpg.Record,
    )


def test_corsia_eventi_lascia_sempre_connessioni_ai_comandi():
    for max_size in (3, 5, 10, 30):
        assert 1 <= connessioni_per_eventi(max_size) <= max_size - min(2, max_size - 1)
    assert connessioni_per_eventi(10) == 7


async def test_pool_pieno_non_attende_per_sempre(monkeypatch):
    monkeypatch.setattr(pool_db, "TIMEOUT_COMANDI_SECONDI", 0.3)
    pool = await _pool(max_size=2)
    try:
        a, b = await pool.acquire(), await pool.acquire()
        inizio = asyncio.get_running_loop().time()
        with pytest.raises(asyncio.TimeoutError):
            await pool.fetchval("SELECT 1")
        assert asyncio.get_running_loop().time() - inizio < 2
        await pool.release(a)
        await pool.release(b)
        assert await pool.fetchval("SELECT 1") == 1
    finally:
        await pool.close()


async def test_gli_eventi_non_prendono_tutto_il_pool(monkeypatch):
    monkeypatch.setattr(pool_db, "TIMEOUT_EVENTI_SECONDI", 0.3)
    pool = await _pool(max_size=3)  # eventi: 1 connessione, 2 sempre libere per i comandi
    try:
        corsia_db.set(CORSIA_EVENTI)
        evento = await pool.acquire()
        with pytest.raises(asyncio.TimeoutError):
            await pool.acquire()  # il secondo evento aspetta e scade
        corsia_db.set(pool_db.CORSIA_COMANDI)
        c1 = await asyncio.wait_for(pool.acquire(), 1)  # un comando passa subito
        c2 = await asyncio.wait_for(pool.acquire(), 1)
        for con in (c1, c2, evento):
            await pool.release(con)
        corsia_db.set(CORSIA_EVENTI)
        assert await pool.fetchval("SELECT 1") == 1  # il semaforo è stato restituito
        assert pool._connessioni_eventi == set()
    finally:
        corsia_db.set(pool_db.CORSIA_COMANDI)
        await pool.close()


async def test_errore_nella_connessione_restituisce_il_semaforo(monkeypatch):
    pool = await _pool(max_size=3)
    try:
        corsia_db.set(CORSIA_EVENTI)

        async def guasta(self, timeout):
            raise RuntimeError("connessione rifiutata")

        monkeypatch.setattr(pool_db.asyncpg.Pool, "_acquire", guasta)
        with pytest.raises(RuntimeError):
            await pool.acquire()
        assert pool._semaforo_eventi._value == connessioni_per_eventi(3)
    finally:
        corsia_db.set(pool_db.CORSIA_COMANDI)
        monkeypatch.undo()
        await pool.close()


async def test_controlli_lenti_rispondono_riprova_dopo_poco(monkeypatch):
    monkeypatch.setattr(blacklist_tree, "TEMPO_MASSIMO_CONTROLLI", 0.05)
    albero = blacklist_tree.BlacklistAwareCommandTree.__new__(blacklist_tree.BlacklistAwareCommandTree)

    async def lenti(self, interaction):
        await asyncio.sleep(5)

    monkeypatch.setattr(blacklist_tree.BlacklistAwareCommandTree, "_controlli", lenti)
    monkeypatch.setattr(blacklist_tree, "testo_per", AsyncMock(return_value="occupato"))
    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    assert await albero.interaction_check(interaction) is False
    interaction.response.send_message.assert_awaited_once_with("occupato", ephemeral=True)


async def test_sospensione_in_cache_e_dimenticata_alla_scrittura(clean_db, monkeypatch):
    from core.database import db

    monkeypatch.setattr(db, "_pool", clean_db)
    assert await es.attiva_in_cache(1, 2) is None  # «nessuna sospensione» entra in memoria
    await es.sospendi(1, 2, "spam", timedelta(days=1), 9)
    assert await es.attiva_in_cache(1, 2) is not None  # la scrittura ha dimenticato la copia
    # La seconda lettura non va al database.
    letture = []
    originale = es.attiva

    async def conta(*a, **k):
        letture.append(1)
        return await originale(*a, **k)

    monkeypatch.setattr(es, "attiva", conta)
    await es.attiva_in_cache(1, 2)
    await es.attiva_in_cache(1, 2)
    assert letture == []
    await es.riabilita(1, 2)
    assert await es.attiva_in_cache(1, 2) is None


async def test_errore_di_attesa_del_database_risponde_bot_occupato(monkeypatch):
    from discord import app_commands

    from core import premium

    monkeypatch.setattr(premium, "lingua_interazione", AsyncMock(return_value="it"))
    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    monkeypatch.setattr(premium, "_cancella_segnaposto_pubblico", AsyncMock())
    errore = app_commands.CommandInvokeError(MagicMock(), asyncio.TimeoutError())
    await premium.handle_app_command_error(interaction, errore)
    testo = interaction.response.send_message.await_args.args[0]
    assert testo == premium.t("err_bot_occupato", "it") and "occupato" in testo


async def test_il_bot_mette_gli_eventi_nella_corsia_eventi():
    import main

    visto = []

    async def evento():
        visto.append(corsia_db.get())

    bot = main.iYokaiBot.__new__(main.iYokaiBot)
    await asyncio.create_task(main.iYokaiBot._run_event(bot, evento, "on_message"))
    assert visto == [CORSIA_EVENTI]
    assert corsia_db.get() != CORSIA_EVENTI  # il contesto del test non è toccato
