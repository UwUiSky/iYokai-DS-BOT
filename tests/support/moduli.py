"""
tests/support/moduli.py
=======================
Attiva un modulo per i server di un test, con lo stesso metodo che usa
/setup in produzione (Database.set_module_active_for_guild).
"""

from __future__ import annotations

import asyncpg

from core.bounded_cache import BoundedCache

MODULO_LIVELLI = "leveling"


async def attiva_livelli(monkeypatch, pool: asyncpg.Pool, *guild_ids: int) -> None:
    """
    Collega il database globale al pool del test e attiva il modulo
    "leveling" nei server indicati. La cache dei moduli viene sostituita
    per la durata del test (monkeypatch la rimette a posto), così uno
    stato "attivo" non passa da un test all'altro.
    """
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", pool)
    monkeypatch.setattr(database_module.db, "_modules_cache", BoundedCache(max_size=1000))
    for guild_id in guild_ids:
        await database_module.db.set_module_active_for_guild(guild_id, MODULO_LIVELLI, True)


async def togli_configurazione(pool: asyncpg.Pool, *guild_ids: int) -> None:
    """Per i test che non usano clean_db: cancella le righe di configurazione create da attiva_livelli."""
    await pool.execute("DELETE FROM guild_config_history WHERE guild_id = ANY($1::bigint[])", list(guild_ids))
    await pool.execute("DELETE FROM guild_config WHERE guild_id = ANY($1::bigint[])", list(guild_ids))
