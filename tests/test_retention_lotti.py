"""
tests/test_retention_lotti.py
=============================
La retention cancella a lotti e non si inceppa: un server grande avanza a ogni giro, uno che sbaglia non
ferma gli altri, un rientro durante il lavoro lo ferma, e ogni tabella del registro regge il lotto.
Funzioni coperte: consiglio 25/11/2026, seri di stabilità (blocco C)
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from core import data_registry as reg
from core import retention_worker as lavoro
from tests.test_retention_worker import ADESSO, G, ALTRO, _conta, _dati_del_server, presenza  # noqa: F401


async def _tante_righe(pool, guild_id, n):
    await pool.execute(
        "INSERT INTO leveling_totals (guild_id, user_id, xp_total) SELECT $1, g, 5 FROM generate_series(100, $2) g",
        guild_id, 99 + n,
    )


async def test_un_server_grande_si_cancella_a_lotti(clean_db, presenza):
    await _dati_del_server(clean_db, G)
    await _tante_righe(clean_db, G, 2500)
    await presenza.segna_uscito(G, ADESSO - timedelta(days=100))
    istruzioni = []
    originale = lavoro._lotto_del_server

    async def conta(pool, guild_id, soglia, sql):
        istruzioni.append(sql)
        return await originale(pool, guild_id, soglia, sql)

    lavoro._lotto_del_server, prima = conta, lavoro._lotto_del_server
    try:
        tolte = await lavoro.purga_server(clean_db, G, ADESSO, lotto=1000)
    finally:
        lavoro._lotto_del_server = prima
    assert tolte["leveling_totals"] == 2501
    assert sum(1 for s in istruzioni if "leveling_totals" in s) == 3  # 1000 + 1000 + 501
    assert await _conta(clean_db, "leveling_totals", "guild_id", G) == 0
    assert (await presenza.get(G))["purged_at"] is not None


async def test_tempo_finito_conserva_i_lotti_fatti_e_il_giorno_dopo_riprende(clean_db, presenza):
    await _tante_righe(clean_db, G, 3000)
    await presenza.segna_uscito(G, ADESSO - timedelta(days=100))
    with pytest.raises(lavoro.TempoFinito):
        await lavoro.purga_server(clean_db, G, ADESSO, lotto=500, tempo_massimo=0.0)
    assert (await presenza.get(G))["purged_at"] is None  # non segnato fatto: si riprende
    tolte = await lavoro.purga_server(clean_db, G, ADESSO, lotto=500)  # il giro dopo
    assert tolte["leveling_totals"] == 3000
    assert (await presenza.get(G))["purged_at"] is not None


async def test_un_server_che_sbaglia_non_ferma_gli_altri(clean_db, presenza, monkeypatch):
    for g in (G, ALTRO):
        await _dati_del_server(clean_db, g)
        await presenza.segna_uscito(g, ADESSO - timedelta(days=100))
    vero = lavoro.purga_server

    async def sbaglia_per_G(pool, guild_id, adesso=None, *a, **k):
        if guild_id == G:
            raise asyncio.TimeoutError()  # non è un PostgresError: prima uccideva tutto il giro
        return await vero(pool, guild_id, adesso, *a, **k)

    monkeypatch.setattr(lavoro, "purga_server", sbaglia_per_G)
    for _ in range(5):  # qualunque ordine casuale: l'altro server si cancella sempre
        risultato = await lavoro.giro(clean_db, set(), ADESSO)
        if ALTRO in risultato["server"]:
            break
    assert ALTRO in risultato["server"] and G not in risultato["server"]
    assert (await presenza.get(G))["purged_at"] is None  # G resta da cancellare


async def test_un_rientro_durante_il_lavoro_lo_ferma(clean_db, presenza):
    await _tante_righe(clean_db, G, 2000)
    await presenza.segna_uscito(G, ADESSO - timedelta(days=100))
    originale = lavoro._lotto_del_server
    chiamate = []

    async def rientra_dopo_il_primo(pool, guild_id, soglia, sql):
        chiamate.append(1)
        if len(chiamate) == 2:
            await presenza.segna_entrato(guild_id)  # il bot rientra a metà
        return await originale(pool, guild_id, soglia, sql)

    lavoro._lotto_del_server = rientra_dopo_il_primo
    try:
        assert await lavoro.purga_server(clean_db, G, ADESSO, lotto=500) is None
    finally:
        lavoro._lotto_del_server = originale
    riga = await presenza.get(G)
    assert riga["left_at"] is None and riga["purged_at"] is None


async def test_ogni_tabella_del_registro_regge_il_lotto(clean_db):
    """Le DELETE a lotti sono SQL valido su ogni tabella dichiarata (anche con filtri speciali)."""
    esistenti = {r["table_name"] for r in await clean_db.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    provate = 0
    for t in reg.REGISTRO:
        if t.nome not in esistenti:
            continue
        sql = t.sql_cancella_server_a_lotti(10)
        if sql is not None:
            await clean_db.execute(sql, 123456)
            provate += 1
        if t.scadenza is not None:
            await clean_db.execute(t.sql_scaduti_a_lotti(10), t.scadenza.giorni)
            provate += 1
    assert provate > 100


async def test_le_scadute_si_tolgono_a_lotti(clean_db, presenza):
    tabella = next(t for t in reg.tabelle_con_scadenza() if t.nome == "tempban_stato")
    await clean_db.execute(
        "INSERT INTO tempban_stato (guild_id, user_id, modo, finisce_il) "
        f"SELECT 1, g, 'rientro', now() - make_interval(days => {tabella.scadenza.giorni + 5}) FROM generate_series(1, 2500) g"
    )
    tolte = await lavoro.pulisci_scaduti(clean_db, lotto=1000)
    assert tolte.get("tempban_stato") == 2500
