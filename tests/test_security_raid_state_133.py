"""
tests/test_security_raid_state_133.py
=====================================
M 10.16 (#133): durante un raid i messaggi di benvenuto privati si
sospendono. Qui: lo stato "raid in corso" che l'anti-raid aggiorna e
che il benvenuto interroga.
"""

from datetime import timedelta

import core.security_raid_state as stato
from tests.test_anti_raid_f1 import (  # noqa: F401  (fixture condivise)
    GUILD_ID,
    INIZIO,
    _azione,
    _raid,
    cog,
    db_finto,
    orologio,
    server,
)


async def test_nessun_raid_di_default():
    assert stato.raid_in_corso(424242, INIZIO) is False


async def test_ingresso_di_raid_segna_il_server_e_passa_dopo_il_blocco(cog, server, orologio):
    await _azione(cog, "quarantine")
    stato.azzera(GUILD_ID)

    await _raid(cog, server, quanti=2)  # sotto soglia: non è raid
    assert stato.raid_in_corso(GUILD_ID) is False

    await _raid(cog, server, quanti=2, primo_id=300)  # oltre soglia
    assert stato.raid_in_corso(GUILD_ID) is True

    orologio(seconds=stato.DURATA_RAID_SECONDI + 1)
    assert stato.raid_in_corso(GUILD_ID) is False


async def test_blocco_chiuso_azzera_lo_stato(cog, server, orologio):
    await _azione(cog, "both")
    await _raid(cog, server, quanti=3)
    assert stato.raid_in_corso(GUILD_ID) is True

    orologio(minutes=16)
    await cog.ripristina_blocchi_scaduti(INIZIO + timedelta(minutes=16))

    assert stato.raid_in_corso(GUILD_ID) is False
