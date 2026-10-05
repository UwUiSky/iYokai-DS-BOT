"""
tests/test_trasferimenti_incrociati.py
======================================
M 9.16: due trasferimenti opposti (A→B e B→A) partiti insieme non
devono bloccarsi a vicenda, né tra utenti né tra tesorerie di clan. In
più: il giorno dell'XP vocale si calcola in UTC, non nell'ora locale
della macchina.
Funzioni coperte: SPEC §15.2, §15.14
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

from core.repositories.guild_clan_repo import GuildClanRepository
from core.repositories.leveling_repo import LevelingRepository
from tests.support.concorrenza import apri_connessioni

GUILD_ID = 100
GIRI = 10


@pytest.mark.asyncio
async def test_pay_incrociati_insieme_non_vanno_in_stallo(clean_db):
    await apri_connessioni(clean_db)
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    await repo.add_coins(GUILD_ID, 1, 1000)
    await repo.add_coins(GUILD_ID, 2, 1000)

    for _ in range(GIRI):
        esiti = await asyncio.gather(
            repo.transfer_coins(GUILD_ID, 1, 2, 30),
            repo.transfer_coins(GUILD_ID, 2, 1, 10),
        )
        assert esiti == [True, True]

    assert (await repo.get_totals(GUILD_ID, 1)).coins_total == 1000 - 20 * GIRI
    assert (await repo.get_totals(GUILD_ID, 2)).coins_total == 1000 + 20 * GIRI


@pytest.mark.asyncio
async def test_trasferimenti_incrociati_tra_tesorerie_non_vanno_in_stallo(clean_db):
    await apri_connessioni(clean_db)
    repo = GuildClanRepository(pool_provider=lambda: clean_db)
    scadenza = datetime.now(timezone.utc) + timedelta(hours=24)
    # Stesso capo, due server: una sola gilda per server per utente.
    primo = await repo.create_clan(GUILD_ID, "AAA", "Primo", 1, scadenza)
    secondo = await repo.create_clan(GUILD_ID + 1, "BBB", "Secondo", 1, scadenza)
    await repo.donate(primo, 1, 20_000)
    await repo.donate(secondo, 1, 20_000)

    for _ in range(GIRI):
        esiti = await asyncio.gather(
            repo.transfer_between_treasuries(primo, secondo, 30),
            repo.transfer_between_treasuries(secondo, primo, 10),
        )
        assert esiti == [True, True]

    assert (await repo.get_clan(primo)).treasury_balance == 5_000 - 20 * GIRI
    assert (await repo.get_clan(secondo)).treasury_balance == 5_000 + 20 * GIRI


@pytest.mark.asyncio
async def test_il_giorno_dell_xp_vocale_e_in_utc(clean_db, monkeypatch):
    # Si sceglie un fuso in cui la data locale è diversa da quella UTC
    # in questo preciso momento (nomi POSIX: il segno è al contrario).
    adesso_utc = datetime.now(timezone.utc)
    monkeypatch.setenv("TZ", "LOC-14" if adesso_utc.hour >= 12 else "LOC12")
    time.tzset()
    try:
        repo = LevelingRepository(pool_provider=lambda: clean_db)
        await repo.add_voice_minute(GUILD_ID, 1, current_channel_id=5, is_eligible=True)
        giorno_salvato = await clean_db.fetchval(
            "SELECT voice_activity_date FROM leveling_totals WHERE guild_id = $1 AND user_id = 1",
            GUILD_ID,
        )
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()

    assert giorno_salvato == adesso_utc.date()
