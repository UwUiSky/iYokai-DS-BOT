"""
tests/test_escalation_crescita.py
=================================
AMD-070 (#116): il timeout oltre l'ultimo gradino dura base x moltiplicatore
alla ricaduta, con tetto di ricadute e di 28 giorni. Database vero.
"""

import pytest

import cogs.automod.escalation as modulo_escalation
from core.escalation_ladder_logic import (
    MAX_TIMEOUT_SECONDI,
    LadderStep,
    get_ladder_action,
    timeout_che_cresce,
)
from core.repositories.escalation_repo import EscalationRepository
from tests.support.discord_fakes import fake_guild, fake_interaction

SCALA = [LadderStep(1, "warn"), LadderStep(2, "timeout", 600)]


def test_senza_moltiplicatore_la_durata_resta_fissa():
    assert get_ladder_action(6, SCALA).duration_seconds == 600


def test_sul_gradino_la_durata_e_quella_di_base():
    assert get_ladder_action(2, SCALA, 2.0, 5).duration_seconds == 600


def test_oltre_l_ultimo_gradino_la_durata_cresce():
    assert get_ladder_action(3, SCALA, 2.0, 5).duration_seconds == 1200
    assert get_ladder_action(5, SCALA, 2.0, 5).duration_seconds == 4800


def test_il_tetto_di_ricadute_ferma_la_crescita():
    assert get_ladder_action(50, SCALA, 2.0, 3).duration_seconds == 600 * 8


def test_mai_oltre_28_giorni():
    passo = timeout_che_cresce(LadderStep(1, "timeout", 7 * 24 * 3600), 10, 10.0, 10)
    assert passo.duration_seconds == MAX_TIMEOUT_SECONDI


def test_kick_e_ban_non_crescono():
    scala = [LadderStep(1, "kick")]
    assert get_ladder_action(4, scala, 3.0, 5) == scala[0]


@pytest.fixture
def repo(clean_db, monkeypatch) -> EscalationRepository:
    vero = EscalationRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo_escalation, "escalation_repo", vero)
    return vero


async def test_enable_salva_moltiplicatore_e_tetto(repo):
    cog = modulo_escalation.EscalationCog(bot=None)
    interazione = fake_interaction(guild=fake_guild(guild_id=100))

    await cog.enable.callback(cog, interazione, None, 2.5, 4)
    config = await repo.get_config(100)
    assert (config.enabled, config.moltiplicatore, config.tetto_strike) == (True, 2.5, 4)

    # Una seconda chiamata col solo tetto lascia il moltiplicatore com'è.
    await cog.enable.callback(cog, fake_interaction(guild=fake_guild(guild_id=100)), None, None, 2)
    config = await repo.get_config(100)
    assert (config.moltiplicatore, config.tetto_strike) == (2.5, 2)


async def test_di_base_il_timeout_non_cresce(repo):
    config = await repo.get_config(100)
    assert (config.moltiplicatore, config.tetto_strike) == (1.0, 5)
