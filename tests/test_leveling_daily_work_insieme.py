"""
tests/test_leveling_daily_work_insieme.py
=========================================
BUG-14 (#35): due /daily (o due /work) mandati insieme devono dare un
solo premio. Le due chiamate girano davvero in parallelo sul database
di test.
Funzioni coperte: SPEC §15.2
"""

import asyncio

import pytest

import cogs.leveling.leveling as leveling_module
from cogs.leveling.leveling import LevelingCog
from core.leveling_logic import (
    DAILY_REWARD_COINS,
    WORK_REWARD_MAX,
    WORK_REWARD_MIN,
    period_key,
)
from core.repositories.leveling_repo import LevelingRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

GUILD_ID = 100
USER_ID = 1


@pytest.fixture
async def cog_e_repo(clean_db, monkeypatch):
    # Si aprono prima tutte le connessioni del pool: così le due chiamate
    # partono davvero insieme e nessuna aspetta l'apertura di una
    # connessione.
    await asyncio.gather(*(clean_db.fetchval("SELECT pg_sleep(0.05)") for _ in range(3)))
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(leveling_module, "leveling_repo", repo)
    cog = LevelingCog(bot=None)
    cog.cog_unload()
    return cog, repo


def _interazione():
    return fake_interaction(guild=fake_guild(GUILD_ID), user=fake_member(USER_ID))


def _testi(interazione) -> list[str]:
    return [chiamata.args[0] for chiamata in interazione.response.send_message.call_args_list]


@pytest.mark.asyncio
async def test_due_daily_insieme_danno_un_solo_premio(cog_e_repo):
    cog, repo = cog_e_repo
    prima, seconda = _interazione(), _interazione()

    await asyncio.gather(
        cog.daily.callback(cog, prima),
        cog.daily.callback(cog, seconda),
    )

    totali = await repo.get_totals(GUILD_ID, USER_ID)
    assert totali.coins_total == DAILY_REWARD_COINS
    risposte = _testi(prima) + _testi(seconda)
    assert sum("Hai riscosso" in testo for testo in risposte) == 1
    assert sum("già riscosso" in testo for testo in risposte) == 1


@pytest.mark.asyncio
async def test_due_work_insieme_danno_un_solo_premio(cog_e_repo):
    cog, repo = cog_e_repo
    prima, seconda = _interazione(), _interazione()

    await asyncio.gather(
        cog.work.callback(cog, prima),
        cog.work.callback(cog, seconda),
    )

    totali = await repo.get_totals(GUILD_ID, USER_ID)
    assert WORK_REWARD_MIN <= totali.coins_total <= WORK_REWARD_MAX
    risposte = _testi(prima) + _testi(seconda)
    assert sum("guadagnato" in testo for testo in risposte) == 1
    assert sum("Sei stanco" in testo for testo in risposte) == 1


@pytest.mark.asyncio
async def test_daily_conta_anche_nella_classifica_del_mese(cog_e_repo):
    cog, repo = cog_e_repo

    await cog.daily.callback(cog, _interazione())

    voci = await repo.top_coins_period(GUILD_ID, period=period_key())
    assert [(voce.user_id, voce.amount) for voce in voci] == [(USER_ID, DAILY_REWARD_COINS)]


@pytest.mark.asyncio
async def test_daily_dopo_il_tempo_di_attesa_si_riscuote_di_nuovo(cog_e_repo):
    cog, repo = cog_e_repo
    await cog.daily.callback(cog, _interazione())
    # Si sposta indietro l'ultima riscossione: è passato più di un giorno.
    await repo._pool.execute(
        "UPDATE leveling_totals SET last_daily_at = last_daily_at - interval '25 hours'"
    )

    await cog.daily.callback(cog, _interazione())

    assert (await repo.get_totals(GUILD_ID, USER_ID)).coins_total == 2 * DAILY_REWARD_COINS
