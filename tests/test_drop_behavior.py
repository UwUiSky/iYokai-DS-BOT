"""
tests/test_drop_behavior.py
===============================
Test del comportamento REALE dei drop di coin (SPEC.md §15.6) —
on_message che li fa comparire (con random.random() mockato per
controllare il roll) e il pulsante di raccolta, contro PostgreSQL
vero per il saldo.
"""

from unittest.mock import patch

import discord
import pytest

from cogs.leveling.leveling import LevelingCog, MODULE_LEVELING
from core.database import Database
from core.repositories.leveling_repo import LevelingRepository


class _FakeMember:
    def __init__(self, member_id: int, bot: bool = False, display_name: str = "Utente") -> None:
        self.id = member_id
        self.bot = bot
        self.mention = f"<@{member_id}>"
        self.display_name = display_name


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeChannel:
    def __init__(self) -> None:
        self.sent_views: list = []
        self.sent_contents: list[str] = []

    async def send(self, content: str = None, view=None) -> None:
        self.sent_contents.append(content)
        self.sent_views.append(view)


class _FakeMessage:
    def __init__(self, author, guild, channel) -> None:
        self.author = author
        self.guild = guild
        self.channel = channel


class _FakeInteractionResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.edited_views: list = []

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append(content)

    async def edit_message(self, view=None) -> None:
        self.edited_views.append(view)


class _FakeButtonInteraction:
    def __init__(self, user) -> None:
        self.user = user
        self.response = _FakeInteractionResponse()


@pytest.fixture
async def cog_e_database(monkeypatch):
    import cogs.leveling.leveling as leveling_module

    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.ensure_guild_exists(100)
    await database.set_module_active_for_guild(100, MODULE_LEVELING, True)

    repo = LevelingRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(leveling_module, "leveling_repo", repo)
    monkeypatch.setattr(leveling_module, "db", database)

    class _RewardRepoFinto:
        async def get_rewards_up_to_level(self, guild_id, level):
            return []

    monkeypatch.setattr(leveling_module, "level_reward_repo", _RewardRepoFinto())

    cog = LevelingCog(bot=None)
    cog.cog_unload()

    yield cog, repo, database
    await database.pool.execute("DELETE FROM leveling_totals")
    await database.pool.execute("DELETE FROM leveling_activity")
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 100")
    await database.close()


@pytest.mark.asyncio
async def test_roll_favorevole_manda_il_drop(cog_e_database):
    cog, repo, database = cog_e_database
    canale = _FakeChannel()
    messaggio = _FakeMessage(_FakeMember(1), _FakeGuild(100), canale)

    with patch("cogs.leveling.leveling.random.random", return_value=0.0001):
        await cog.on_message(messaggio)

    assert len(canale.sent_views) == 1
    assert "drop di" in canale.sent_contents[0]
    assert canale.sent_views[0].amount > 0


@pytest.mark.asyncio
async def test_roll_sfavorevole_non_manda_nulla(cog_e_database):
    cog, repo, database = cog_e_database
    canale = _FakeChannel()
    messaggio = _FakeMessage(_FakeMember(1), _FakeGuild(100), canale)

    with patch("cogs.leveling.leveling.random.random", return_value=0.9):
        await cog.on_message(messaggio)

    assert canale.sent_views == []


@pytest.mark.asyncio
async def test_raccogliere_il_drop_accredita_i_coin(cog_e_database):
    cog, repo, database = cog_e_database
    view = cog.DropClaimView(guild_id=100, amount=42)
    bottone = view.children[0]

    raccoglitore = _FakeMember(5)
    interazione = _FakeButtonInteraction(raccoglitore)

    await bottone.callback(interazione)

    totali = await repo.get_totals(100, 5)
    assert totali.coins_total == 42
    assert view.claimed_by == 5
    assert bottone.disabled is True


@pytest.mark.asyncio
async def test_secondo_click_non_accredita_di_nuovo(cog_e_database):
    cog, repo, database = cog_e_database
    view = cog.DropClaimView(guild_id=100, amount=42)
    bottone = view.children[0]

    primo = _FakeButtonInteraction(_FakeMember(5))
    await bottone.callback(primo)

    secondo_utente = _FakeMember(6)
    secondo = _FakeButtonInteraction(secondo_utente)
    await bottone.callback(secondo)

    assert "già stato raccolto" in secondo.response.sent_messages[0]
    totali_secondo = await repo.get_totals(100, 6)
    assert totali_secondo.coins_total == 0
