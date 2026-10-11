"""
tests/test_command_usage_repo.py
================================
Tabella `command_usage` (migrazione 0022): una riga per server e utente con
l'ULTIMO comando usato, tetto di righe e pulizia dei dati vecchi.
Funzioni coperte: NF-06 (issue #147)
"""

from __future__ import annotations

import pytest

from core.repositories.command_usage_repo import CommandUsageRepository


@pytest.fixture
async def repo(clean_db, db_pool):
    return CommandUsageRepository(lambda: db_pool)


async def test_una_riga_per_server_e_utente_con_l_ultimo_comando(repo, db_pool):
    await repo.registra(1, 10, "fun gioca")
    await repo.registra(1, 10, "mod avvisa")
    await repo.registra(2, 10, "level top")
    assert await repo.ultimo(1, 10) == "mod avvisa"
    assert await repo.ultimo(2, 10) == "level top"
    assert await repo.ultimo(1, 11) is None
    assert await db_pool.fetchval("SELECT count(*) FROM command_usage") == 2


async def test_in_dm_usa_guild_zero(repo):
    await repo.registra(None, 10, "utility ping")
    assert await repo.ultimo(None, 10) == "utility ping"
    assert await repo.ultimo(0, 10) == "utility ping"


async def test_il_percorso_viene_tagliato_a_100_caratteri(repo):
    await repo.registra(1, 10, "x" * 300)
    assert len(await repo.ultimo(1, 10)) == 100


async def test_pulizia_toglie_le_righe_vecchie(repo, db_pool):
    await repo.registra(1, 10, "a")
    await repo.registra(1, 11, "b")
    await db_pool.execute("UPDATE command_usage SET used_at = now() - interval '200 days' WHERE user_id = 10")
    tolte = await repo.pulisci(giorni=90, tetto=1000)
    assert tolte == 1
    assert await repo.ultimo(1, 10) is None
    assert await repo.ultimo(1, 11) == "b"


async def test_pulizia_rispetta_il_tetto_tenendo_le_piu_recenti(repo, db_pool):
    for utente in range(1, 8):
        await repo.registra(1, utente, f"c{utente}")
        await db_pool.execute(
            "UPDATE command_usage SET used_at = now() - make_interval(mins => $2) WHERE user_id = $1",
            utente,
            utente,
        )
    await repo.pulisci(giorni=90, tetto=3)
    assert await db_pool.fetchval("SELECT count(*) FROM command_usage") == 3
    assert await repo.ultimo(1, 1) == "c1"  # la più recente resta
    assert await repo.ultimo(1, 7) is None


async def test_la_pulizia_parte_da_sola_ogni_n_scritture(repo, db_pool):
    repo.ogni_n_scritture = 3
    repo.giorni = 90
    await repo.registra(1, 1, "a")
    await db_pool.execute("UPDATE command_usage SET used_at = now() - interval '200 days'")
    await repo.registra(1, 2, "b")
    await repo.registra(1, 3, "c")
    assert await repo.ultimo(1, 1) is None


async def test_la_migrazione_0022_crea_la_tabella(db_pool, clean_db):
    colonne = {
        r["column_name"]
        for r in await db_pool.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'command_usage'"
        )
    }
    assert {"guild_id", "user_id", "command_path", "used_at"} <= colonne
