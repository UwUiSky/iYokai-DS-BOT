"""
M 14.12 (DB-2): sciogliere un clan o togliere un giveaway non lascia righe orfane.
"""

import asyncpg
import pytest


async def _clan(pool, guild_id=1):
    await pool.execute(
        "INSERT INTO clans (guild_id,tag,name,owner_id,officialize_deadline) VALUES ($1,'T','C',5,now())", guild_id
    )
    return await pool.fetchval("SELECT id FROM clans ORDER BY id DESC LIMIT 1")


@pytest.mark.asyncio
async def test_sciogliere_un_clan_toglie_tutte_le_righe_figlie(clean_db):
    clan = await _clan(clean_db)
    await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES ($1,1,5,'owner')", clan)
    await clean_db.execute("INSERT INTO clan_treasury_ledger (clan_id,user_id,amount,reason) VALUES ($1,5,1,'x')", clan)
    await clean_db.execute("INSERT INTO clan_monthly_xp (clan_id,guild_id,period_key,xp_gained) VALUES ($1,1,'2026-10',3)", clan)

    await clean_db.execute("DELETE FROM clans WHERE id = $1", clan)

    for tabella in ("clan_members", "clan_treasury_ledger", "clan_monthly_xp"):
        assert await clean_db.fetchval(f"SELECT count(*) FROM {tabella}") == 0, tabella


@pytest.mark.asyncio
async def test_non_si_aggiunge_un_membro_a_un_clan_che_non_esiste(clean_db):
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await clean_db.execute("INSERT INTO clan_members (clan_id,guild_id,user_id,role) VALUES (999,1,5,'member')")


@pytest.mark.asyncio
async def test_togliere_un_giveaway_toglie_gli_iscritti(clean_db):
    await clean_db.execute(
        "INSERT INTO giveaways (guild_id,channel_id,prize,winners_count,ends_at,created_by) VALUES (1,2,'p',1,now(),3)"
    )
    giveaway = await clean_db.fetchval("SELECT id FROM giveaways")
    await clean_db.execute("INSERT INTO giveaway_entries (giveaway_id,user_id) VALUES ($1,5)", giveaway)

    await clean_db.execute("DELETE FROM giveaways WHERE id = $1", giveaway)

    assert await clean_db.fetchval("SELECT count(*) FROM giveaway_entries") == 0
