"""
tests/test_database.py
=========================
A differenza degli altri test, qui NON usiamo la fixture clean_db
(che duplica manualmente le CREATE TABLE base per evitare di aprire
un secondo pool globale) — usiamo direttamente la classe Database
vera di core/database.py, connect()/run_migrations()/close() incluso.

Serve a intercettare esattamente il tipo di errore che una copia
manuale delle query non intercetterebbe mai: un errore di sintassi
o un riferimento sbagliato nel collegamento reale tra
Database.run_migrations() e scheduler.run_migrations().
"""

import os

import pytest

from core.database import Database


@pytest.mark.asyncio
async def test_database_connect_e_migrazioni_reali():
    database = Database()
    await database.connect()
    try:
        # Se run_migrations() ha un errore SQL (incluso quello dello
        # scheduler, ora collegato in sequenza), questa chiamata
        # solleva un'eccezione e il test fallisce qui.
        await database.run_migrations()

        # Verifica concreta: le tabelle attese esistono davvero.
        tabelle_attese = [
            "guild_config",
            "premium_whitelist",
            "premium_module_flags",
            "scheduled_actions",
        ]
        for tabella in tabelle_attese:
            exists = await database.pool.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", f"public.{tabella}"
            )
            assert exists is True, f"Tabella mancante dopo le migrazioni: {tabella}"

        # run_migrations() deve poter essere richiamata più volte
        # senza errori (è quello che succede ad ogni riavvio del
        # bot): IF NOT EXISTS deve reggere davvero, non solo a parole.
        await database.run_migrations()
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_ensure_guild_exists_e_whitelist_reali():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()

        # Pulizia mirata per questo test, per non dipendere
        # dall'ordine di esecuzione degli altri test del file.
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 999999999"
        )
        await database.pool.execute(
            "DELETE FROM premium_whitelist WHERE guild_id = 999999999"
        )

        await database.ensure_guild_exists(999999999)
        row = await database.pool.fetchrow(
            "SELECT guild_id, setup_completed FROM guild_config WHERE guild_id = $1",
            999999999,
        )
        assert row is not None
        assert row["setup_completed"] is False

        # Chiamarlo due volte non deve fallire né duplicare la riga
        # (ON CONFLICT DO NOTHING).
        await database.ensure_guild_exists(999999999)
        count = await database.pool.fetchval(
            "SELECT count(*) FROM guild_config WHERE guild_id = $1", 999999999
        )
        assert count == 1

        assert await database.is_guild_whitelisted(999999999) is False
        await database.add_guild_to_whitelist(999999999, added_by=1, reason="test")
        assert await database.is_guild_whitelisted(999999999) is True
        await database.remove_guild_from_whitelist(999999999)
        assert await database.is_guild_whitelisted(999999999) is False
    finally:
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id = 999999999"
        )
        await database.close()
