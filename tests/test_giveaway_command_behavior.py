"""
tests/test_giveaway_command_behavior.py
===========================================
Test del comportamento REALE di /giveaway (creazione) e della view
di partecipazione — contro PostgreSQL vero.
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from cogs.leveling.leveling import LevelingCog
from core.database import Database
from core.repositories.giveaway_repo import GiveawayRepository
from core.repositories.leveling_repo import LevelingRepository


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_embeds: list = []
        self.sent_views: list = []

    async def send_message(self, content: str = None, embed=None, view=None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if embed is not None:
            self.sent_embeds.append(embed)
        self.sent_views.append(view)


class _FakeOriginalMessage:
    id = 12345


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeChannel:
    id = 500


class _FakeInteraction:
    def __init__(self, guild_id: int | None, user=None) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.channel = _FakeChannel() if guild_id is not None else None
        self.user = user
        self.response = _FakeResponse()

    async def original_response(self):
        return _FakeOriginalMessage()


class _FakeMember:
    def __init__(self, member_id: int, roles=None) -> None:
        self.id = member_id
        self.roles = roles or []


class _FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id


@pytest.fixture
async def cog_e_repos(monkeypatch):
    import cogs.leveling.leveling as leveling_module

    database = Database()
    await database.connect()
    await database.run_migrations()
    # Stessa pulizia preventiva di test_giveaway_worker.py — righe
    # residue di altri file (che usano clean_db, pulito solo
    # all'inizio di ogni LORO test) sarebbero altrimenti visibili qui.
    await database.pool.execute("DELETE FROM giveaways")
    await database.pool.execute("DELETE FROM giveaway_entries")

    giveaway_repo = GiveawayRepository(pool_provider=lambda: database.pool)
    leveling_repo = LevelingRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(leveling_module, "giveaway_repo", giveaway_repo)
    monkeypatch.setattr(leveling_module, "leveling_repo", leveling_repo)

    cog = LevelingCog(bot=None)
    cog.cog_unload()

    yield cog, giveaway_repo, leveling_repo
    await database.pool.execute("DELETE FROM giveaways")
    await database.pool.execute("DELETE FROM giveaway_entries")
    await database.pool.execute("DELETE FROM leveling_totals")
    await database.close()


@pytest.mark.asyncio
async def test_giveaway_create_salva_e_risponde(cog_e_repos):
    cog, giveaway_repo, leveling_repo = cog_e_repos
    interaction = _FakeInteraction(guild_id=100, user=_FakeMember(1))

    await cog.giveaway.callback(
        cog, interaction, prize="Nitro", duration_minutes=60, winners=1, min_level=0, required_role=None
    )

    assert len(interaction.response.sent_embeds) == 1
    assert "Nitro" in interaction.response.sent_embeds[0].title
    assert interaction.response.sent_views[0].giveaway_id is not None

    giveaway = await giveaway_repo.get_giveaway(interaction.response.sent_views[0].giveaway_id)
    assert giveaway.message_id == 12345
    assert giveaway.prize == "Nitro"


@pytest.mark.asyncio
async def test_entra_senza_requisiti_registra_la_partecipazione(cog_e_repos):
    cog, giveaway_repo, leveling_repo = cog_e_repos
    giveaway_id = await giveaway_repo.create_giveaway(
        100, channel_id=500, prize="X", winners_count=1, min_level=0,
        required_role_id=None, ends_at=datetime.now(timezone.utc) + timedelta(hours=1), created_by=1,
    )

    view = cog.GiveawayEnterView(giveaway_id)
    bottone = view.children[0]

    class _FakeButtonInteraction:
        def __init__(self, user) -> None:
            self.user = user
            self.response = _FakeResponse()

    interazione = _FakeButtonInteraction(_FakeMember(5))
    await bottone.callback(interazione)

    assert "registrata" in interazione.response.sent_messages[0]
    assert await giveaway_repo.has_entered(giveaway_id, user_id=5) is True


@pytest.mark.asyncio
async def test_entra_senza_livello_sufficiente_viene_rifiutato(cog_e_repos):
    cog, giveaway_repo, leveling_repo = cog_e_repos
    giveaway_id = await giveaway_repo.create_giveaway(
        100, channel_id=500, prize="X", winners_count=1, min_level=10,
        required_role_id=None, ends_at=datetime.now(timezone.utc) + timedelta(hours=1), created_by=1,
    )

    view = cog.GiveawayEnterView(giveaway_id)
    bottone = view.children[0]

    class _FakeButtonInteraction:
        def __init__(self, user) -> None:
            self.user = user
            self.response = _FakeResponse()

    interazione = _FakeButtonInteraction(_FakeMember(5))  # livello 0, sotto la soglia
    await bottone.callback(interazione)

    assert "Non soddisfi i requisiti" in interazione.response.sent_messages[0]
    assert await giveaway_repo.has_entered(giveaway_id, user_id=5) is False


@pytest.mark.asyncio
async def test_secondo_click_avvisa_gia_partecipato(cog_e_repos):
    cog, giveaway_repo, leveling_repo = cog_e_repos
    giveaway_id = await giveaway_repo.create_giveaway(
        100, channel_id=500, prize="X", winners_count=1, min_level=0,
        required_role_id=None, ends_at=datetime.now(timezone.utc) + timedelta(hours=1), created_by=1,
    )

    view = cog.GiveawayEnterView(giveaway_id)
    bottone = view.children[0]

    class _FakeButtonInteraction:
        def __init__(self, user) -> None:
            self.user = user
            self.response = _FakeResponse()

    membro = _FakeMember(5)
    await bottone.callback(_FakeButtonInteraction(membro))
    seconda = _FakeButtonInteraction(membro)
    await bottone.callback(seconda)

    assert "già partecipato" in seconda.response.sent_messages[0]
