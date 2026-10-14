"""NF-25 (#96): statistiche di attività. Buffer, sessioni vocali, ruoli per attività, repo."""
from datetime import date, datetime, timedelta, timezone

import pytest

from core.activity_stats_logic import (
    MAX_CHIAVI_BUFFER,
    ActivityBuffer,
    VoiceTracker,
    ruoli_da_aggiornare,
    per_giorno_settimana,
    escluso,
)
from core.repositories.activity_stats_repo import ActivityStatsRepository

G = 700001
T0 = datetime(2026, 10, 14, 15, 30, tzinfo=timezone.utc)


def test_buffer_somma_per_canale_membro_ora():
    b = ActivityBuffer()
    b.add_message(G, 10, 1, T0)
    b.add_message(G, 10, 1, T0)
    b.add_message(G, 11, 2, T0)
    canali, membri, ore = b.drain()
    assert canali[(G, T0.date(), 10)] == [2, 0]
    assert membri[(G, T0.date(), 1)] == [2, 0]
    assert ore[(G, T0.date(), 15)] == [3, 0]
    assert b.drain() == ({}, {}, {})


def test_buffer_pieno_al_tetto():
    b = ActivityBuffer()
    for i in range(MAX_CHIAVI_BUFFER):
        b.add_message(G, 1, i, T0)
    assert b.pieno


def test_sessione_vocale_conta_i_secondi_e_tick_non_conta_due_volte():
    v = VoiceTracker()
    v.entra(G, 5, 99, T0)
    crediti = v.tick(T0 + timedelta(seconds=100))
    assert crediti == [(G, 99, 5, 100)]
    assert v.tick(T0 + timedelta(seconds=130)) == [(G, 99, 5, 30)]
    assert v.esce(G, 99, T0 + timedelta(seconds=150)) == [(G, 99, 5, 20)]
    assert v.tick(T0 + timedelta(seconds=999)) == []


def test_sessione_vocale_tetto_di_un_giorno():
    v = VoiceTracker()
    v.entra(G, 5, 99, T0)
    assert v.tick(T0 + timedelta(days=3))[0][3] == 86400


def test_esclusioni():
    assert escluso(canale_id=1, ruoli_utente={7}, canali_ignorati=[1], ruoli_ignorati=[])
    assert escluso(canale_id=2, ruoli_utente={7}, canali_ignorati=[1], ruoli_ignorati=[7])
    assert not escluso(canale_id=2, ruoli_utente={8}, canali_ignorati=[1], ruoli_ignorati=[7])


def test_ruoli_da_aggiornare_dare_e_togliere_con_tetto():
    dare, togliere = ruoli_da_aggiornare({1, 2, 3}, {3, 4}, rimuovi=True, limite=10)
    assert dare == {1, 2} and togliere == {4}
    dare, togliere = ruoli_da_aggiornare({1, 2, 3}, {3, 4}, rimuovi=False, limite=10)
    assert togliere == set()
    dare, togliere = ruoli_da_aggiornare(set(range(100)), set(), rimuovi=True, limite=5)
    assert len(dare) == 5


def test_giorno_settimana():
    r = per_giorno_settimana({date(2026, 10, 12): 4, date(2026, 10, 19): 6, date(2026, 10, 14): 1})
    assert r[0] == 10 and r[2] == 1 and len(r) == 7  # lunedì, mercoledì


@pytest.fixture
def repo(clean_db):
    return ActivityStatsRepository(pool_provider=lambda: clean_db)


async def _riempi(repo):
    b = ActivityBuffer()
    for _ in range(5):
        b.add_message(G, 10, 1, T0)
    for _ in range(2):
        b.add_message(G, 11, 2, T0)
    b.add_voice(G, 12, 1, 600, T0)
    await repo.flush(*b.drain())


async def test_flush_somma_e_non_duplica(repo):
    await _riempi(repo)
    await _riempi(repo)
    since = T0.date() - timedelta(days=1)
    assert await repo.member_total(G, 1, since, "messages") == 10
    assert await repo.member_total(G, 1, since, "voice_minutes") == 20
    top = await repo.top_channels(G, since, "messages", 5)
    assert top[0] == (10, 10)


async def test_top_membri_con_filtro_di_ruolo_e_periodo(repo):
    await _riempi(repo)
    since = T0.date()
    assert (await repo.top_members(G, since, "messages", 5))[0] == (1, 5)
    assert await repo.top_members(G, since, "messages", 5, solo_utenti={2}) == [(2, 2)]
    assert await repo.top_members(G, T0.date() + timedelta(days=1), "messages", 5) == []


async def test_membri_sopra_soglia_e_ore(repo):
    await _riempi(repo)
    assert await repo.members_over(G, T0.date(), "messages", 3) == {1}
    assert await repo.members_over(G, T0.date(), "voice_minutes", 10) == {1}
    ore = await repo.by_hour(G, T0.date())
    assert ore[15] == 7 and ore[0] == 0 and len(ore) == 24


async def test_regole_ruoli_tetto_e_unicita(repo):
    for i in range(10):
        assert await repo.add_rule(G, 1000 + i, "messages", 50, 7, True)
    assert not await repo.add_rule(G, 2000, "messages", 50, 7, True)  # tetto 10
    assert await repo.add_rule(G, 1000, "voice_minutes", 5, 7, True)  # stesso ruolo: aggiorna
    regole = await repo.list_rules(G)
    assert len(regole) == 10 and {r.metric for r in regole if r.role_id == 1000} == {"voice_minutes"}
    assert await repo.delete_rule(G, regole[0].id)
    assert G in await repo.guilds_with_rules()


async def test_impostazioni_toggle(repo):
    assert await repo.toggle_ignored_channel(G, 5) is True
    assert (await repo.get_settings(G)).ignored_channels == [5]
    assert await repo.toggle_ignored_channel(G, 5) is False
    assert await repo.toggle_ignored_role(G, 9) is True
    assert (await repo.get_settings(G)).ignored_roles == [9]
