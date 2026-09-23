"""
tests/test_guild_clan_voice_worker.py
=========================================
Test di GuildClanVoiceWorker.tick() contro PostgreSQL REALE — clan e
attività vocale creati davvero, non repository finti: verifica che
il tick accrediti per davvero XP/coin, rispetti l'ufficializzazione,
e ripulisca chi è uscito dal vocale.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.guild_clan_voice_worker import GuildClanVoiceWorker
from core.repositories.clan_voice_activity_repo import ClanVoiceActivityRepository
from core.repositories.guild_clan_repo import GuildClanRepository

ORA = datetime.now(timezone.utc)


class _FakeMember:
    def __init__(self, member_id: int, bot: bool = False) -> None:
        self.id = member_id
        self.bot = bot


class _FakeVoiceChannel:
    def __init__(self, channel_id: int, members: list) -> None:
        self.id = channel_id
        self.members = members


class _FakeGuild:
    def __init__(self, guild_id: int, voice_channels: list) -> None:
        self.id = guild_id
        self.voice_channels = voice_channels


class _FakeBot:
    def __init__(self, guilds: list) -> None:
        self.guilds = guilds


@pytest.fixture
async def repos(monkeypatch):
    import core.guild_clan_voice_worker as modulo
    from core.database import Database

    database = Database()
    await database.connect()
    await database.run_migrations()
    # Pulizia PRIMA di creare dati di test: righe residue di altri
    # file (che usano clean_db, pulito solo all'inizio di OGNI LORO
    # test, non alla fine dell'intero file) sarebbero altrimenti
    # visibili qui — stesso bug reale già trovato e corretto per i
    # test dei giveaway in questa stessa sessione.
    await database.pool.execute("DELETE FROM clan_voice_activity")
    await database.pool.execute("DELETE FROM clan_treasury_ledger")
    await database.pool.execute("DELETE FROM clan_members")
    await database.pool.execute("DELETE FROM clans")

    clan_repo = GuildClanRepository(pool_provider=lambda: database.pool)
    activity_repo = ClanVoiceActivityRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(modulo, "guild_clan_repo", clan_repo)
    monkeypatch.setattr(modulo, "clan_voice_activity_repo", activity_repo)

    yield clan_repo, activity_repo
    await database.pool.execute("DELETE FROM clan_voice_activity")
    await database.pool.execute("DELETE FROM clan_treasury_ledger")
    await database.pool.execute("DELETE FROM clan_members")
    await database.pool.execute("DELETE FROM clans")
    await database.close()


async def _crea_clan_ufficializzato(clan_repo, guild_id=100, tag="ABC", owner_id=1):
    clan_id = await clan_repo.create_clan(
        guild_id, tag=tag, name="Clan", owner_id=owner_id,
        officialize_deadline=ORA + timedelta(hours=24),
    )
    await clan_repo.set_officialized(clan_id)
    return clan_id


@pytest.mark.asyncio
async def test_membro_di_clan_ufficializzato_matura_xp_e_coin(repos):
    clan_repo, activity_repo = repos
    clan_id = await _crea_clan_ufficializzato(clan_repo, owner_id=1)

    canale = _FakeVoiceChannel(500, members=[_FakeMember(1)])
    guild = _FakeGuild(100, voice_channels=[canale])

    await GuildClanVoiceWorker().tick(_FakeBot([guild]), now=ORA)

    clan = await clan_repo.get_clan(clan_id)
    assert clan.total_xp == 30
    assert clan.treasury_balance == -15_000 + 2


@pytest.mark.asyncio
async def test_clan_non_ufficializzato_non_matura_nulla(repos):
    clan_repo, activity_repo = repos
    clan_id = await clan_repo.create_clan(
        100, tag="ABC", name="Clan", owner_id=1,
        officialize_deadline=ORA + timedelta(hours=24),
    )
    # NON ufficializzato - ancora in deficit di prova.

    canale = _FakeVoiceChannel(500, members=[_FakeMember(1)])
    guild = _FakeGuild(100, voice_channels=[canale])

    await GuildClanVoiceWorker().tick(_FakeBot([guild]), now=ORA)

    clan = await clan_repo.get_clan(clan_id)
    assert clan.total_xp == 0
    assert clan.treasury_balance == -15_000  # invariato


@pytest.mark.asyncio
async def test_utente_non_membro_di_nessun_clan_viene_ignorato(repos):
    clan_repo, activity_repo = repos
    await _crea_clan_ufficializzato(clan_repo, owner_id=1)

    canale = _FakeVoiceChannel(500, members=[_FakeMember(999)])  # non è nel clan
    guild = _FakeGuild(100, voice_channels=[canale])

    await GuildClanVoiceWorker().tick(_FakeBot([guild]), now=ORA)  # non deve sollevare


@pytest.mark.asyncio
async def test_bot_in_vocale_viene_ignorato(repos):
    clan_repo, activity_repo = repos
    clan_id = await _crea_clan_ufficializzato(clan_repo, owner_id=1)

    canale = _FakeVoiceChannel(500, members=[_FakeMember(1, bot=True)])
    guild = _FakeGuild(100, voice_channels=[canale])

    await GuildClanVoiceWorker().tick(_FakeBot([guild]), now=ORA)

    clan = await clan_repo.get_clan(clan_id)
    assert clan.total_xp == 0


@pytest.mark.asyncio
async def test_membro_uscito_dal_vocale_viene_ripulito(repos):
    clan_repo, activity_repo = repos
    clan_id = await _crea_clan_ufficializzato(clan_repo, owner_id=1)

    canale = _FakeVoiceChannel(500, members=[_FakeMember(1)])
    guild_con_membro = _FakeGuild(100, voice_channels=[canale])
    worker = GuildClanVoiceWorker()

    await worker.tick(_FakeBot([guild_con_membro]), now=ORA)
    attivita = await activity_repo.get_activity(clan_id, user_id=1)
    assert attivita.current_channel_id == 500

    # Secondo tick: il membro non è più in NESSUN canale vocale.
    guild_senza_membro = _FakeGuild(100, voice_channels=[_FakeVoiceChannel(500, members=[])])
    await worker.tick(_FakeBot([guild_senza_membro]), now=ORA)

    attivita_dopo = await activity_repo.get_activity(clan_id, user_id=1)
    assert attivita_dopo.current_channel_id is None
