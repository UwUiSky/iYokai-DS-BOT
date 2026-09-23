"""
tests/test_clan_voice_activity_repo.py
==========================================
Test di ClanVoiceActivityRepository contro PostgreSQL reale.
"""

from datetime import date, timedelta

import pytest

from core.repositories.clan_voice_activity_repo import ClanVoiceActivityRepository

OGGI = date(2026, 9, 23)
IERI = OGGI - timedelta(days=1)


@pytest.fixture
def repo(clean_db):
    return ClanVoiceActivityRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_primo_tick_in_assoluto_tasso_pieno(repo):
    xp, coin = await repo.apply_tick(clan_id=1, user_id=1, channel_id=500, today=OGGI)

    assert xp == 30
    assert coin == 2


@pytest.mark.asyncio
async def test_secondo_tick_stesso_canale_stato_persistito(repo):
    await repo.apply_tick(1, 1, channel_id=500, today=OGGI)
    await repo.apply_tick(1, 1, channel_id=500, today=OGGI)

    attivita = await repo.get_activity(1, 1)
    assert attivita.current_channel_id == 500
    assert attivita.ticks_in_current_channel == 2
    assert attivita.ticks_today == 2


@pytest.mark.asyncio
async def test_decadimento_dopo_novanta_tick_nello_stesso_canale(repo):
    for _ in range(90):
        await repo.apply_tick(1, 1, channel_id=500, today=OGGI)

    # Il tick numero 91 legge "90 tick nello stesso canale" prima di
    # questo tick - fattore di decadimento 0.5 (90/180).
    xp, coin = await repo.apply_tick(1, 1, channel_id=500, today=OGGI)

    assert xp == 15  # 30 * 0.5
    assert coin == 1  # 2 * 0.5


@pytest.mark.asyncio
async def test_cambio_canale_azzera_il_decadimento(repo):
    for _ in range(90):
        await repo.apply_tick(1, 1, channel_id=500, today=OGGI)

    # Cambio canale: il decadimento riparte da zero, tasso pieno,
    # anche se ticks_today continua ad accumularsi.
    xp, coin = await repo.apply_tick(1, 1, channel_id=999, today=OGGI)

    assert xp == 30
    assert coin == 2

    attivita = await repo.get_activity(1, 1)
    assert attivita.ticks_in_current_channel == 1  # riparte da 1 (questo tick)
    assert attivita.ticks_today == 91  # NON azzerato dal cambio canale


@pytest.mark.asyncio
async def test_tetto_giornaliero_azzera_il_guadagno(repo):
    # Alterniamo due canali ad ogni tick per evitare il decadimento
    # da permanenza (già testato a parte sopra) e isolare solo
    # l'effetto del tetto giornaliero - 720 tick PIENI (il tetto),
    # il tick numero 721 deve leggere ticks_today_prima=720 e dare zero.
    for i in range(720):
        await repo.apply_tick(1, 1, channel_id=500 + (i % 2), today=OGGI)

    xp, coin = await repo.apply_tick(1, 1, channel_id=999999, today=OGGI)

    assert (xp, coin) == (0, 0)


@pytest.mark.asyncio
async def test_giorno_diverso_azzera_il_tetto_giornaliero(repo):
    xp_ieri, coin_ieri = await repo.apply_tick(1, 1, channel_id=500, today=IERI)
    assert (xp_ieri, coin_ieri) != (0, 0)  # tasso pieno per il primo tick di ieri

    # Oggi è un giorno diverso: ticks_today deve ripartire da zero,
    # tasso pieno indipendentemente da quanto accumulato ieri.
    xp_oggi, coin_oggi = await repo.apply_tick(1, 1, channel_id=999, today=OGGI)
    assert xp_oggi == 30
    assert coin_oggi == 2


@pytest.mark.asyncio
async def test_clear_activity_azzera_canale_e_decadimento(repo):
    await repo.apply_tick(1, 1, channel_id=500, today=OGGI)
    await repo.apply_tick(1, 1, channel_id=500, today=OGGI)

    await repo.clear_activity(1, 1)

    attivita = await repo.get_activity(1, 1)
    assert attivita.current_channel_id is None
    assert attivita.ticks_in_current_channel == 0


@pytest.mark.asyncio
async def test_clear_activity_non_tocca_ticks_today(repo):
    await repo.apply_tick(1, 1, channel_id=500, today=OGGI)

    await repo.clear_activity(1, 1)

    # Il tetto giornaliero resta valido finché non cambia il giorno -
    # uscire dal vocale non deve "regalare" ticks_today azzerati.
    assert (await repo.get_activity(1, 1)).ticks_today == 1


@pytest.mark.asyncio
async def test_clan_diversi_non_si_influenzano(repo):
    await repo.apply_tick(clan_id=1, user_id=1, channel_id=500, today=OGGI)
    await repo.apply_tick(clan_id=2, user_id=1, channel_id=500, today=OGGI)

    attivita_clan1 = await repo.get_activity(1, 1)
    attivita_clan2 = await repo.get_activity(2, 1)
    assert attivita_clan1.ticks_today == 1
    assert attivita_clan2.ticks_today == 1
