"""
tests/test_guild_clan_text_xp_behavior.py
=============================================
Test del comportamento REALE del lato TESTUALE del guadagno ×2 di
gilda (SPEC.md §15.14) — on_message deve accreditare TEXT_TICK_XP
alla gilda di un membro ufficializzato, in aggiunta (indipendente)
all'XP personale già testata altrove, contro PostgreSQL vero.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from cogs.leveling.leveling import LevelingCog, MODULE_LEVELING
from core.database import Database
from core.guild_clan_logic import TEXT_TICK_XP
from core.repositories.guild_clan_repo import GuildClanRepository
from core.repositories.leveling_repo import LevelingRepository

ORA = datetime.now(timezone.utc)


class _FakeMember:
    def __init__(self, member_id: int, bot: bool = False) -> None:
        self.id = member_id
        self.bot = bot
        self.mention = f"<@{member_id}>"
        self.display_name = "Utente"


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeChannel:
    async def send(self, content: str = None, view=None) -> None:
        pass


class _FakeMessage:
    def __init__(self, author, guild, channel) -> None:
        self.author = author
        self.guild = guild
        self.channel = channel


@pytest.fixture
async def cog_e_repo(monkeypatch):
    import cogs.leveling.leveling as leveling_module

    database = Database()
    await database.connect()
    await database.run_migrations()
    # Pulizia preventiva: questo test usa un Database() locale contro
    # lo stesso Postgres condiviso dagli altri file, non `clean_db` —
    # un'altra suite (es. test_guild_clan_repo.py) può lasciare righe
    # con lo stesso tag "ABC" per la guild 100 se il SUO ultimo test
    # non svuota le tabelle dopo di sé (clean_db pulisce PRIMA di ogni
    # test, non dopo l'ultimo).
    await database.pool.execute("DELETE FROM clan_members")
    await database.pool.execute("DELETE FROM clans")
    await database.ensure_guild_exists(100)
    await database.set_module_active_for_guild(100, MODULE_LEVELING, True)

    leveling_repo = LevelingRepository(pool_provider=lambda: database.pool)
    clan_repo = GuildClanRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(leveling_module, "leveling_repo", leveling_repo)
    monkeypatch.setattr(leveling_module, "guild_clan_repo", clan_repo)
    monkeypatch.setattr(leveling_module, "db", database)

    class _RewardRepoFinto:
        async def get_rewards_up_to_level(self, guild_id, level):
            return []

    monkeypatch.setattr(leveling_module, "level_reward_repo", _RewardRepoFinto())

    cog = LevelingCog(bot=None)
    cog.cog_unload()

    yield cog, clan_repo, database
    await database.pool.execute("DELETE FROM clan_members")
    await database.pool.execute("DELETE FROM clans")
    await database.pool.execute("DELETE FROM leveling_totals")
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 100")
    await database.close()


async def _crea_clan_ufficializzato(clan_repo, owner_id: int) -> int:
    clan_id = await clan_repo.create_clan(
        100, tag="ABC", name="Clan", owner_id=owner_id,
        officialize_deadline=ORA + timedelta(hours=24),
    )
    await clan_repo.set_officialized(clan_id)
    return clan_id


@pytest.mark.asyncio
async def test_messaggio_di_un_membro_di_clan_accredita_xp_di_gilda(cog_e_repo):
    cog, clan_repo, database = cog_e_repo
    clan_id = await _crea_clan_ufficializzato(clan_repo, owner_id=1)
    messaggio = _FakeMessage(_FakeMember(1), _FakeGuild(100), _FakeChannel())

    with patch("cogs.leveling.leveling.random.random", return_value=0.9):
        await cog.on_message(messaggio)

    assert (await clan_repo.get_clan(clan_id)).total_xp == TEXT_TICK_XP


@pytest.mark.asyncio
async def test_secondo_messaggio_entro_il_cooldown_non_accredita_di_nuovo(cog_e_repo):
    cog, clan_repo, database = cog_e_repo
    clan_id = await _crea_clan_ufficializzato(clan_repo, owner_id=1)
    messaggio = _FakeMessage(_FakeMember(1), _FakeGuild(100), _FakeChannel())

    with patch("cogs.leveling.leveling.random.random", return_value=0.9):
        await cog.on_message(messaggio)
        await cog.on_message(messaggio)

    assert (await clan_repo.get_clan(clan_id)).total_xp == TEXT_TICK_XP


@pytest.mark.asyncio
async def test_messaggio_di_chi_non_e_in_nessun_clan_non_tocca_nessuna_gilda(cog_e_repo):
    cog, clan_repo, database = cog_e_repo
    messaggio = _FakeMessage(_FakeMember(42), _FakeGuild(100), _FakeChannel())

    with patch("cogs.leveling.leveling.random.random", return_value=0.9):
        await cog.on_message(messaggio)  # non deve sollevare


@pytest.mark.asyncio
async def test_messaggio_di_membro_di_clan_non_ufficializzato_non_accredita(cog_e_repo):
    cog, clan_repo, database = cog_e_repo
    clan_id = await clan_repo.create_clan(
        100, tag="ABC", name="Clan", owner_id=1,
        officialize_deadline=ORA + timedelta(hours=24),
    )
    # NON ufficializzato - ancora in deficit di prova.
    messaggio = _FakeMessage(_FakeMember(1), _FakeGuild(100), _FakeChannel())

    with patch("cogs.leveling.leveling.random.random", return_value=0.9):
        await cog.on_message(messaggio)

    assert (await clan_repo.get_clan(clan_id)).total_xp == 0
