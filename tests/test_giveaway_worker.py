"""
tests/test_giveaway_worker.py
=================================
Test di GiveawayWorker.tick() contro PostgreSQL reale.
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from core.database import Database
from core.giveaway_worker import GiveawayWorker
from core.repositories.giveaway_repo import GiveawayRepository

ORA = datetime.now(timezone.utc)


class _FakeChannel(discord.TextChannel):
    def __init__(self, channel_id: int, fallisce: bool = False) -> None:
        self.id = channel_id
        self.sent_texts: list[str] = []
        self._fallisce = fallisce

    async def send(self, content: str) -> None:
        if self._fallisce:
            raise discord.HTTPException(response=_FakeHttpResponse(), message="errore finto")
        self.sent_texts.append(content)


class _FakeHttpResponse:
    status = 500
    reason = "errore finto"


class _FakeGuild:
    def __init__(self, guild_id: int, channel) -> None:
        self.id = guild_id
        self._channel = channel

    def get_channel(self, channel_id: int):
        return self._channel


class _FakeBot:
    def __init__(self, guild) -> None:
        self._guild = guild

    def get_guild(self, guild_id: int):
        return self._guild


@pytest.fixture
async def repo(monkeypatch):
    import core.giveaway_worker as modulo

    database = Database()
    await database.connect()
    await database.run_migrations()
    # Pulizia PRIMA di creare dati di test: clean_db (usata da altri
    # file, es. test_giveaway_repo.py) svuota solo all'inizio di
    # OGNI SUO test, non alla fine dell'intero file - una riga
    # lasciata dall'ultimo test di quel file sarebbe altrimenti
    # visibile qui (trovato per davvero: un giveaway "Server Boost"
    # residuo falsava il conteggio dei messaggi annunciati).
    await database.pool.execute("DELETE FROM giveaways")
    await database.pool.execute("DELETE FROM giveaway_entries")

    giveaway_repo = GiveawayRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(modulo, "giveaway_repo", giveaway_repo)

    yield giveaway_repo
    await database.pool.execute("DELETE FROM giveaways")
    await database.pool.execute("DELETE FROM giveaway_entries")
    await database.close()


@pytest.mark.asyncio
async def test_estrae_e_annuncia_i_vincitori(repo):
    giveaway_id = await repo.create_giveaway(
        100, channel_id=500, prize="Nitro", winners_count=1, min_level=0,
        required_role_id=None, ends_at=ORA - timedelta(minutes=1), created_by=1,
    )
    await repo.add_entry(giveaway_id, user_id=1)
    await repo.add_entry(giveaway_id, user_id=2)

    canale = _FakeChannel(500)
    await GiveawayWorker().tick(_FakeBot(_FakeGuild(100, canale)), now=ORA)

    assert len(canale.sent_texts) == 1
    assert "Nitro" in canale.sent_texts[0]
    assert (await repo.get_giveaway(giveaway_id)).ended is True


@pytest.mark.asyncio
async def test_nessun_partecipante_annuncia_comunque_senza_vincitori(repo):
    giveaway_id = await repo.create_giveaway(
        100, channel_id=500, prize="Nitro", winners_count=1, min_level=0,
        required_role_id=None, ends_at=ORA - timedelta(minutes=1), created_by=1,
    )

    canale = _FakeChannel(500)
    await GiveawayWorker().tick(_FakeBot(_FakeGuild(100, canale)), now=ORA)

    assert "nessuno ha partecipato" in canale.sent_texts[0]


@pytest.mark.asyncio
async def test_giveaway_non_ancora_scaduto_viene_ignorato(repo):
    await repo.create_giveaway(
        100, channel_id=500, prize="Nitro", winners_count=1, min_level=0,
        required_role_id=None, ends_at=ORA + timedelta(hours=1), created_by=1,
    )

    canale = _FakeChannel(500)
    await GiveawayWorker().tick(_FakeBot(_FakeGuild(100, canale)), now=ORA)

    assert canale.sent_texts == []


@pytest.mark.asyncio
async def test_canale_sparito_segna_comunque_concluso(repo):
    giveaway_id = await repo.create_giveaway(
        100, channel_id=500, prize="Nitro", winners_count=1, min_level=0,
        required_role_id=None, ends_at=ORA - timedelta(minutes=1), created_by=1,
    )

    await GiveawayWorker().tick(_FakeBot(_FakeGuild(100, channel=None)), now=ORA)

    assert (await repo.get_giveaway(giveaway_id)).ended is True
