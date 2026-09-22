"""
tests/test_shop_behavior.py
===============================
Test del comportamento REALE di /shop list|buy|add-item|remove-item
— contro PostgreSQL vero.
"""

import discord
import pytest

from cogs.leveling.leveling import LevelingCog
from core.database import Database
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.shop_repo import ShopRepository


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


class _FakeMember(discord.Member):
    def __init__(self, member_id: int) -> None:
        self._id_finto = member_id
        self.chiamate_add_roles: list = []

    @property
    def id(self):
        return self._id_finto

    async def add_roles(self, *roles, reason=None) -> None:
        self.chiamate_add_roles.append(roles)


class _FakeInteraction:
    def __init__(self, guild_id: int | None, user=None) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.user = user or _FakeMember(1)
        self.response = _FakeResponse()


@pytest.fixture
async def cog_e_repos(monkeypatch):
    import cogs.leveling.leveling as leveling_module

    database = Database()
    await database.connect()
    await database.run_migrations()

    shop_repo = ShopRepository(pool_provider=lambda: database.pool)
    leveling_repo = LevelingRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(leveling_module, "shop_repo", shop_repo)
    monkeypatch.setattr(leveling_module, "leveling_repo", leveling_repo)

    cog = LevelingCog(bot=None)
    cog.cog_unload()

    yield cog, shop_repo, leveling_repo
    await database.pool.execute("DELETE FROM shop_items")
    await database.pool.execute("DELETE FROM shop_purchases")
    await database.pool.execute("DELETE FROM leveling_totals")
    await database.close()


@pytest.mark.asyncio
async def test_add_item_e_list(cog_e_repos):
    cog, shop_repo, leveling_repo = cog_e_repos
    interaction_add = _FakeInteraction(guild_id=100)

    await cog.shop_add_item.callback(
        cog, interaction_add, name="Ruolo VIP", price=100, role=None, description=None
    )
    assert "Aggiunto" in interaction_add.response.sent_messages[0]

    interaction_list = _FakeInteraction(guild_id=100)
    await cog.shop_list.callback(cog, interaction_list)

    assert "Ruolo VIP" in interaction_list.response.sent_embeds[0].description


@pytest.mark.asyncio
async def test_list_vuota(cog_e_repos):
    cog, shop_repo, leveling_repo = cog_e_repos
    interaction = _FakeInteraction(guild_id=100)

    await cog.shop_list.callback(cog, interaction)

    assert "vuoto" in interaction.response.sent_messages[0].lower()


@pytest.mark.asyncio
async def test_buy_con_saldo_sufficiente_sottrae_coin(cog_e_repos):
    cog, shop_repo, leveling_repo = cog_e_repos
    item_id = await shop_repo.add_item(100, name="X", price=50)
    await leveling_repo.add_coins(100, 1, 100)

    membro = _FakeMember(1)
    interaction = _FakeInteraction(guild_id=100, user=membro)

    await cog.shop_buy.callback(cog, interaction, item_id=item_id)

    assert "acquistato" in interaction.response.sent_messages[0]
    totali = await leveling_repo.get_totals(100, 1)
    assert totali.coins_total == 50


@pytest.mark.asyncio
async def test_buy_saldo_insufficiente_avvisa_e_non_sottrae(cog_e_repos):
    cog, shop_repo, leveling_repo = cog_e_repos
    item_id = await shop_repo.add_item(100, name="X", price=500)
    await leveling_repo.add_coins(100, 1, 10)

    membro = _FakeMember(1)
    interaction = _FakeInteraction(guild_id=100, user=membro)

    await cog.shop_buy.callback(cog, interaction, item_id=item_id)

    assert "Non hai abbastanza coin" in interaction.response.sent_messages[0]
    totali = await leveling_repo.get_totals(100, 1)
    assert totali.coins_total == 10


@pytest.mark.asyncio
async def test_buy_oggetto_con_ruolo_lo_assegna(cog_e_repos):
    cog, shop_repo, leveling_repo = cog_e_repos
    item_id = await shop_repo.add_item(100, name="VIP", price=10, role_id=999)
    await leveling_repo.add_coins(100, 1, 50)

    membro = _FakeMember(1)
    interaction = _FakeInteraction(guild_id=100, user=membro)

    await cog.shop_buy.callback(cog, interaction, item_id=item_id)

    assert len(membro.chiamate_add_roles) == 1


@pytest.mark.asyncio
async def test_buy_oggetto_con_ruolo_gia_posseduto_avvisa(cog_e_repos):
    cog, shop_repo, leveling_repo = cog_e_repos
    item_id = await shop_repo.add_item(100, name="VIP", price=10, role_id=999)
    await leveling_repo.add_coins(100, 1, 50)
    await shop_repo.record_purchase(100, user_id=1, item_id=item_id)

    membro = _FakeMember(1)
    interaction = _FakeInteraction(guild_id=100, user=membro)

    await cog.shop_buy.callback(cog, interaction, item_id=item_id)

    assert "già acquistato" in interaction.response.sent_messages[0]
    # Non deve aver sottratto coin per un secondo acquisto rifiutato.
    totali = await leveling_repo.get_totals(100, 1)
    assert totali.coins_total == 50


@pytest.mark.asyncio
async def test_buy_id_inesistente_avvisa(cog_e_repos):
    cog, shop_repo, leveling_repo = cog_e_repos
    interaction = _FakeInteraction(guild_id=100)

    await cog.shop_buy.callback(cog, interaction, item_id=99999)

    assert "Nessun oggetto trovato" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_remove_item(cog_e_repos):
    cog, shop_repo, leveling_repo = cog_e_repos
    item_id = await shop_repo.add_item(100, name="X", price=10)

    interaction = _FakeInteraction(guild_id=100)
    await cog.shop_remove_item.callback(cog, interaction, item_id=item_id)

    assert "rimosso" in interaction.response.sent_messages[0].lower()
    assert await shop_repo.list_items(100) == []
