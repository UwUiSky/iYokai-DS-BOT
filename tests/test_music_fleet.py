"""
tests/test_music_fleet.py
=============================
Test di MusicFleet contro PostgreSQL reale (music_session_repo) —
non solo la logica pura di find_free_worker già testata, ma il
comportamento reale di assegnazione/riuso/rilascio.
"""

import pytest

from core.music_fleet import MusicFleet
from core.repositories.music_session_repo import MusicSessionRepository


class _FakeGuildRef:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeWorkerBot:
    def __init__(self, worker_index: int, absent_from: set[int] | None = None) -> None:
        self.worker_index = worker_index
        self.user = _FakeUser(1000 + worker_index)
        # Guild da cui questo worker è "assente" (non invitato) —
        # di default nessuna, cioè presente ovunque, comportamento
        # identico a prima che il controllo di presenza esistesse.
        self._absent_from = absent_from or set()

    def get_guild(self, guild_id: int) -> _FakeGuildRef | None:
        if guild_id in self._absent_from:
            return None
        return _FakeGuildRef(guild_id)


@pytest.fixture
def fleet_e_repo(clean_db, monkeypatch):
    import core.music_fleet as music_fleet_module

    repo = MusicSessionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(music_fleet_module, "music_session_repo", repo)

    worker_bots = [_FakeWorkerBot(i) for i in range(1, 6)]
    fleet = MusicFleet(worker_bots)
    return fleet, repo


@pytest.mark.asyncio
async def test_primo_play_assegna_il_worker_1(fleet_e_repo):
    fleet, repo = fleet_e_repo

    risultato = await fleet.get_or_assign_worker_for_guild(guild_id=100)

    assert risultato is not None
    indice, bot_worker = risultato
    assert indice == 1
    assert bot_worker.worker_index == 1


@pytest.mark.asyncio
async def test_secondo_server_prende_il_worker_2(fleet_e_repo):
    fleet, repo = fleet_e_repo

    await fleet.get_or_assign_worker_for_guild(guild_id=100)
    indice2, _ = await fleet.get_or_assign_worker_for_guild(guild_id=200)

    assert indice2 == 2


@pytest.mark.asyncio
async def test_stesso_server_riusa_lo_stesso_worker(fleet_e_repo):
    fleet, repo = fleet_e_repo

    indice_primo, _ = await fleet.get_or_assign_worker_for_guild(guild_id=100)
    indice_secondo, _ = await fleet.get_or_assign_worker_for_guild(guild_id=100)

    assert indice_primo == indice_secondo


@pytest.mark.asyncio
async def test_tutti_i_worker_occupati_restituisce_none(fleet_e_repo):
    fleet, repo = fleet_e_repo

    for guild_id in range(1, 6):
        await fleet.get_or_assign_worker_for_guild(guild_id)

    risultato = await fleet.get_or_assign_worker_for_guild(guild_id=999)
    assert risultato is None


@pytest.mark.asyncio
async def test_release_libera_il_worker_per_il_prossimo(fleet_e_repo):
    fleet, repo = fleet_e_repo

    for guild_id in range(1, 6):
        await fleet.get_or_assign_worker_for_guild(guild_id)

    await fleet.release_guild(guild_id=3)  # aveva il worker 3

    indice, _ = await fleet.get_or_assign_worker_for_guild(guild_id=999)
    assert indice == 3


@pytest.mark.asyncio
async def test_get_worker_for_guild_senza_sessione_restituisce_none(fleet_e_repo):
    fleet, repo = fleet_e_repo

    risultato = await fleet.get_worker_for_guild(guild_id=999)

    assert risultato is None


@pytest.mark.asyncio
async def test_get_worker_for_guild_non_assegna_un_worker_nuovo(fleet_e_repo):
    fleet, repo = fleet_e_repo

    await fleet.get_worker_for_guild(guild_id=999)  # sola lettura

    # Nessuna sessione deve essere stata creata dalla semplice lettura.
    assert await repo.get_worker_for_guild(999) is None


@pytest.mark.asyncio
async def test_get_worker_for_guild_trova_una_sessione_esistente(fleet_e_repo):
    fleet, repo = fleet_e_repo

    await fleet.get_or_assign_worker_for_guild(guild_id=100)

    risultato = await fleet.get_worker_for_guild(guild_id=100)
    assert risultato is not None
    indice, bot_worker = risultato
    assert indice == 1


def test_get_worker_bot_indice_1_based():
    worker_bots = [_FakeWorkerBot(i) for i in range(1, 6)]
    fleet = MusicFleet(worker_bots)

    assert fleet.get_worker_bot(1).worker_index == 1
    assert fleet.get_worker_bot(5).worker_index == 5


def test_costruttore_rifiuta_un_numero_sbagliato_di_worker():
    with pytest.raises(ValueError):
        MusicFleet([_FakeWorkerBot(1), _FakeWorkerBot(2)])  # solo 2, ne servono 5


# ----------------------------------------------------------------------
# Presenza del worker nel server (SPEC.md §9, cap istanze concorrenti)
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_non_presente_nel_server_viene_escluso_dall_assegnazione(clean_db, monkeypatch):
    import core.music_fleet as music_fleet_module

    repo = MusicSessionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(music_fleet_module, "music_session_repo", repo)

    # Il worker 1 (il primo che verrebbe scelto normalmente) non è
    # invitato in questo server - deve saltare direttamente al 2.
    worker_bots = [_FakeWorkerBot(1, absent_from={100}), *[_FakeWorkerBot(i) for i in range(2, 6)]]
    fleet = MusicFleet(worker_bots)

    indice, _ = await fleet.get_or_assign_worker_for_guild(guild_id=100)

    assert indice == 2


@pytest.mark.asyncio
async def test_worker_assente_da_tutti_i_server_lascia_nessuno_libero(clean_db, monkeypatch):
    import core.music_fleet as music_fleet_module

    repo = MusicSessionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(music_fleet_module, "music_session_repo", repo)

    worker_bots = [_FakeWorkerBot(i, absent_from={999}) for i in range(1, 6)]
    fleet = MusicFleet(worker_bots)

    risultato = await fleet.get_or_assign_worker_for_guild(guild_id=999)

    assert risultato is None


@pytest.mark.asyncio
async def test_get_missing_worker_indices_nessuno_mancante(fleet_e_repo):
    fleet, repo = fleet_e_repo

    assert await fleet.get_missing_worker_indices(guild_id=100) == set()


@pytest.mark.asyncio
async def test_get_missing_worker_indices_alcuni_mancanti(clean_db, monkeypatch):
    import core.music_fleet as music_fleet_module

    repo = MusicSessionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(music_fleet_module, "music_session_repo", repo)

    worker_bots = [
        _FakeWorkerBot(1, absent_from={100}),
        _FakeWorkerBot(2, absent_from={100}),
        *[_FakeWorkerBot(i) for i in range(3, 6)],
    ]
    fleet = MusicFleet(worker_bots)

    assert await fleet.get_missing_worker_indices(guild_id=100) == {1, 2}


def test_build_invite_url_contiene_il_client_id_e_la_guild():
    worker_bots = [_FakeWorkerBot(i) for i in range(1, 6)]
    fleet = MusicFleet(worker_bots)

    url = fleet.build_invite_url(worker_index=3, guild_id=555)

    assert str(1003) in url  # user.id del worker 3 (1000 + 3)
    assert "555" in url
    assert url.startswith("https://discord.com/oauth2/authorize")
