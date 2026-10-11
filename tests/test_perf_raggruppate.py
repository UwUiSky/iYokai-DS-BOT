"""
tests/test_perf_raggruppate.py
==================================
M 9.18 (PERF-4, PERF-6): decadimento e XP vocale non lavorano più utente
per utente. Il risultato deve restare quello di prima: qui si confronta
con le funzioni pure di core/leveling_logic.py.
"""

from datetime import datetime, timezone

import pytest

from core.leveling_logic import apply_weekly_personal_decay
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository

PERIODO = "2026-W40"
NATI_PRIMA_DI = datetime(2099, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


async def _inserisci(clean_db, guild_id: int, saldi: list[int]) -> None:
    await clean_db.executemany(
        "INSERT INTO leveling_totals (guild_id, user_id, coins_total) VALUES ($1, $2, $3)",
        [(guild_id, i + 1, saldo) for i, saldo in enumerate(saldi)],
    )


@pytest.mark.asyncio
async def test_decadimento_di_un_server_uguale_alla_funzione_pura_per_ogni_saldo(repo, clean_db):
    # Saldi da 0 a 600: compresi tutti i casi "mezzo" (5, 15, 25...) dove
    # Python arrotonda al pari e un round() di SQL arrotonderebbe in su.
    saldi = list(range(0, 600))
    await _inserisci(clean_db, 100, saldi)

    utenti, tolti = await repo.apply_weekly_decay_guild(100, PERIODO, NATI_PRIMA_DI)

    righe = await clean_db.fetch(
        "SELECT user_id, coins_total, last_weekly_decay_period FROM leveling_totals "
        "WHERE guild_id = 100 ORDER BY user_id"
    )
    attesi = [apply_weekly_personal_decay(s) for s in saldi]
    assert [r["coins_total"] for r in righe] == attesi
    assert tolti == sum(saldi) - sum(attesi)
    # Chi ha saldo <= 1 non viene toccato né marcato.
    assert utenti == sum(1 for s in saldi if s > 1)
    assert all(r["last_weekly_decay_period"] == PERIODO for r in righe if r["coins_total"] > 1 or r["user_id"] > 2)


@pytest.mark.asyncio
async def test_decadimento_non_tocca_gli_altri_server_e_scrive_in_cassa(repo, clean_db):
    await _inserisci(clean_db, 100, [500, 200])
    await _inserisci(clean_db, 200, [1000])

    utenti, tolti = await repo.apply_weekly_decay_guild(100, PERIODO, NATI_PRIMA_DI)

    assert (utenti, tolti) == (2, 70)
    assert (await repo.get_totals(200, 1)).coins_total == 1000
    cassa = GuildChestRepository(pool_provider=lambda: clean_db)
    assert await cassa.get_balance(100) == 70
    assert await cassa.get_balance(200) == 0


@pytest.mark.asyncio
async def test_decadimento_ripetuto_nello_stesso_periodo_non_fa_nulla(repo, clean_db):
    await _inserisci(clean_db, 100, [500])
    await repo.apply_weekly_decay_guild(100, PERIODO, NATI_PRIMA_DI)

    assert await repo.apply_weekly_decay_guild(100, PERIODO, NATI_PRIMA_DI) == (0, 0)
    assert (await repo.get_totals(100, 1)).coins_total == 450


@pytest.mark.asyncio
async def test_decadimento_salta_chi_e_appena_arrivato(repo, clean_db):
    await _inserisci(clean_db, 100, [500])
    prima = datetime(2000, 1, 1, tzinfo=timezone.utc)

    assert await repo.apply_weekly_decay_guild(100, PERIODO, prima) == (0, 0)
    assert (await repo.get_totals(100, 1)).coins_total == 500


@pytest.mark.asyncio
async def test_elenco_dei_server_da_decadere_senza_doppioni(repo, clean_db):
    await _inserisci(clean_db, 100, [500, 600])
    await _inserisci(clean_db, 200, [1])  # saldo al minimo: niente da fare
    await _inserisci(clean_db, 300, [900])

    assert sorted(await repo.list_guilds_needing_weekly_decay(PERIODO, NATI_PRIMA_DI)) == [100, 300]


# ----------------------------------------------------------------------
# XP vocale: un solo giro di scrittura per server
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_xp_vocale_di_piu_utenti_in_una_chiamata(repo, clean_db):
    risultati = await repo.add_voice_minutes(
        100, [(1, 5000, True), (2, 5000, False), (3, 6000, True)]
    )

    assert set(risultati) == {1, 2, 3}
    assert risultati[1] is not None and risultati[1].xp_granted > 0
    assert risultati[2] is None  # non idoneo
    assert risultati[3] is not None
    assert (await repo.get_totals(100, 1)).xp_total == risultati[1].xp_granted
    assert (await repo.get_totals(100, 2)).xp_total == 0
    canale = await clean_db.fetchval(
        "SELECT voice_channel_id FROM leveling_totals WHERE guild_id = 100 AND user_id = 2"
    )
    assert canale == 5000  # il canale si traccia anche senza guadagno


@pytest.mark.asyncio
async def test_xp_vocale_a_piu_minuti_si_accumula_come_prima(repo, clean_db):
    for _ in range(3):
        await repo.add_voice_minutes(100, [(1, 5000, True), (2, 5000, True)])
    await repo.add_voice_minutes(100, [(2, 6000, True)])  # cambio canale

    consecutivi = {
        r["user_id"]: r["voice_consecutive_minutes"]
        for r in await clean_db.fetch(
            "SELECT user_id, voice_consecutive_minutes FROM leveling_totals WHERE guild_id = 100"
        )
    }
    assert consecutivi == {1: 3, 2: 1}


@pytest.mark.asyncio
async def test_xp_vocale_con_elenco_vuoto_non_fa_nulla(repo):
    assert await repo.add_voice_minutes(100, []) == {}


@pytest.mark.asyncio
async def test_blacklist_di_molti_utenti_con_una_query(clean_db):
    from core.repositories.blacklist_repo import BlacklistRepository

    blacklist = BlacklistRepository(pool_provider=lambda: clean_db)
    await blacklist.add_user(2, "x", 1)
    await blacklist.add_user(4, "x", 1)

    assert await blacklist.blacklisted_among([1, 2, 3, 4]) == {2, 4}
    assert await blacklist.blacklisted_among([]) == set()
    # La cache si riempie: il secondo giro non rilegge dal database.
    await clean_db.execute("DELETE FROM user_blacklist")
    assert await blacklist.blacklisted_among([1, 2, 3, 4]) == {2, 4}
