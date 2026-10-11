"""
tests/test_database_cache.py
============================
M 14.9: gara nella cache dei moduli (letto vecchio che torna in cache dopo una
scrittura; due cambi insieme sullo stesso server).
M 14.10 (PERF-1): le impostazioni del server si leggono una volta sola, finché
nessuno le cambia.
"""

import asyncio
import json

import pytest

import core.database as database_module

GUILD = 4242


class _PoolConConteggio:
    """Pool vero con un contatore delle letture e un cancello opzionale su una lettura."""

    def __init__(self, vero):
        self._vero = vero
        self.letture: list[str] = []
        self.cancello: asyncio.Event | None = None
        self.fermo_su: str | None = None
        self.arrivato = asyncio.Event()

    def __getattr__(self, nome):
        return getattr(self._vero, nome)

    async def fetchrow(self, query, *args):
        riga = await self._vero.fetchrow(query, *args)
        self.letture.append(query)
        if self.fermo_su and self.fermo_su in query and self.cancello is not None:
            self.arrivato.set()
            await self.cancello.wait()
            self.fermo_su = None
        return riga


@pytest.fixture
def db(clean_db, monkeypatch):
    istanza = database_module.db
    pool = _PoolConConteggio(clean_db)
    monkeypatch.setattr(istanza, "_pool", pool)
    istanza._modules_cache.clear()
    istanza._settings_cache.clear()
    yield istanza, pool
    istanza._modules_cache.clear()
    istanza._settings_cache.clear()


async def test_lettura_lenta_non_rimette_in_cache_un_valore_vecchio(db):
    istanza, pool = db
    await istanza.ensure_guild_exists(GUILD)
    pool.cancello = asyncio.Event()
    pool.fermo_su = "SELECT modules FROM guild_config"

    lettore = asyncio.create_task(istanza.is_module_active_for_guild(GUILD, "xp"))
    await pool.arrivato.wait()  # ha già letto "xp spento" ma non l'ha ancora messo in cache
    await istanza.set_module_active_for_guild(GUILD, "xp", True)
    pool.cancello.set()
    assert await lettore is False  # il suo valore era vecchio, va bene

    assert await istanza.is_module_active_for_guild(GUILD, "xp") is True  # ma non resta in cache


async def test_due_cambi_insieme_lasciano_uno_storico_coerente(db):
    istanza, _ = db
    await istanza.ensure_guild_exists(GUILD)

    await asyncio.gather(
        istanza.set_module_active_for_guild(GUILD, "xp", True),
        istanza.set_module_active_for_guild(GUILD, "xp", False),
    )

    storico = sorted(await istanza.get_config_history(GUILD, limit=10), key=lambda e: e.id)
    assert len(storico) == 2
    assert storico[1].old_value == storico[0].new_value  # il secondo parte da dove ha finito il primo
    finale = await istanza.pool.fetchval("SELECT (modules -> 'xp')::boolean FROM guild_config WHERE guild_id=$1", GUILD)
    assert finale is storico[1].new_value
    assert await istanza.is_module_active_for_guild(GUILD, "xp") is finale


# ----------------------------------------------------------------------
# Impostazioni del server in memoria
# ----------------------------------------------------------------------
def _letture_settings(pool):
    return [q for q in pool.letture if "settings" in q and "FROM guild_config" in q]


async def test_la_seconda_lettura_non_tocca_il_database(db):
    istanza, pool = db
    await istanza.set_guild_setting(GUILD, "canale", 7)
    pool.letture.clear()

    assert await istanza.get_guild_setting(GUILD, "canale") == 7
    assert await istanza.get_guild_setting(GUILD, "canale") == 7
    assert await istanza.get_guild_setting(GUILD, "altra", default="x") == "x"

    assert len(_letture_settings(pool)) == 1


async def test_una_scrittura_dimentica_la_cache(db):
    istanza, _ = db
    await istanza.set_guild_setting(GUILD, "canale", 7)
    assert await istanza.get_guild_setting(GUILD, "canale") == 7

    await istanza.set_guild_setting(GUILD, "canale", 8)
    assert await istanza.get_guild_setting(GUILD, "canale") == 8

    await istanza.remove_guild_setting(GUILD, "canale", None)
    assert await istanza.get_guild_setting(GUILD, "canale", default="niente") == "niente"


async def test_import_e_reset_dimenticano_la_cache(db):
    istanza, _ = db
    await istanza.set_guild_setting(GUILD, "canale", 7)
    assert await istanza.get_guild_setting(GUILD, "canale") == 7

    await istanza.import_full_config(GUILD, {}, {"canale": 9}, "it")
    assert await istanza.get_guild_setting(GUILD, "canale") == 9

    await istanza.reset_guild_config(GUILD)
    assert await istanza.get_guild_setting(GUILD, "canale") is None


async def test_chi_modifica_la_lista_ricevuta_non_sporca_la_cache(db):
    istanza, _ = db
    await istanza.set_guild_setting(GUILD, "ruoli", [1, 2])
    lista = await istanza.get_guild_setting(GUILD, "ruoli")
    lista.append(99)

    assert await istanza.get_guild_setting(GUILD, "ruoli") == [1, 2]


async def test_la_cache_scade(db, monkeypatch):
    istanza, pool = db
    await istanza.set_guild_setting(GUILD, "canale", 7)
    adesso = [1000.0]
    monkeypatch.setattr(database_module, "_monotonic", lambda: adesso[0])
    await istanza.get_guild_setting(GUILD, "canale")
    pool.letture.clear()

    adesso[0] += database_module.SETTINGS_CACHE_TTL_SECONDS + 1
    await istanza.get_guild_setting(GUILD, "canale")

    assert len(_letture_settings(pool)) == 1


async def test_server_senza_riga_restituisce_il_default(db):
    istanza, _ = db
    assert await istanza.get_guild_setting(999_001, "qualsiasi", default=5) == 5
