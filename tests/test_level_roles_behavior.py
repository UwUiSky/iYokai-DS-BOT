"""
tests/test_level_roles_behavior.py
======================================
Test del comportamento REALE di /level-roles add|remove|list —
contro PostgreSQL vero.
"""

import pytest

from cogs.leveling.leveling import LevelingCog
from core.database import Database


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_embeds: list = []

    async def send_message(self, content: str = None, embed=None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if embed is not None:
            self.sent_embeds.append(embed)


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id
        self.mention = f"<@&{role_id}>"


class _FakeInteraction:
    def __init__(self, guild_id: int | None) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.response = _FakeResponse()


@pytest.fixture
async def cog_e_database(monkeypatch):
    import cogs.leveling.leveling as leveling_module
    from core.repositories.level_reward_repo import LevelRewardRepository

    database = Database()
    await database.connect()
    await database.run_migrations()

    repo = LevelRewardRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(leveling_module, "level_reward_repo", repo)

    cog = LevelingCog(bot=None)
    cog.cog_unload()  # ferma subito il task periodico avviato nel costruttore

    yield cog, repo
    await database.pool.execute("DELETE FROM level_reward_roles")
    await database.close()


@pytest.mark.asyncio
async def test_add_e_list(cog_e_database):
    cog, repo = cog_e_database
    interaction_add = _FakeInteraction(guild_id=100)

    await cog.level_roles_add.callback(cog, interaction_add, level=10, role=_FakeRole(555))

    assert "livello **10**" in interaction_add.response.sent_messages[0]

    interaction_list = _FakeInteraction(guild_id=100)
    await cog.level_roles_list.callback(cog, interaction_list)

    assert "livello **10**" in interaction_list.response.sent_embeds[0].description


@pytest.mark.asyncio
async def test_list_vuota(cog_e_database):
    cog, repo = cog_e_database
    interaction = _FakeInteraction(guild_id=100)

    await cog.level_roles_list.callback(cog, interaction)

    assert "Nessun ruolo-premio" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_remove(cog_e_database):
    cog, repo = cog_e_database
    reward_id = await repo.add_reward(100, level_threshold=5, role_id=1)

    interaction = _FakeInteraction(guild_id=100)
    await cog.level_roles_remove.callback(cog, interaction, reward_id=reward_id)

    assert "rimosso" in interaction.response.sent_messages[0].lower()
    assert await repo.list_rewards(100) == []


@pytest.mark.asyncio
async def test_remove_inesistente_avvisa(cog_e_database):
    cog, repo = cog_e_database
    interaction = _FakeInteraction(guild_id=100)

    await cog.level_roles_remove.callback(cog, interaction, reward_id=99999)

    assert "Nessun ruolo-premio trovato" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_add_fuori_da_un_server_rifiuta(cog_e_database):
    cog, repo = cog_e_database
    interaction = _FakeInteraction(guild_id=None)

    await cog.level_roles_add.callback(cog, interaction, level=5, role=_FakeRole(1))

    assert "solo dentro un server" in interaction.response.sent_messages[0]
