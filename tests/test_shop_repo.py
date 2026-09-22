"""
tests/test_shop_repo.py
===========================
Test di ShopRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.shop_repo import ShopRepository


@pytest.fixture
def repo(clean_db):
    return ShopRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_add_item_e_list_items(repo):
    await repo.add_item(100, name="Ruolo VIP", price=500, role_id=555, description="Accesso VIP")

    oggetti = await repo.list_items(100)
    assert len(oggetti) == 1
    assert oggetti[0].name == "Ruolo VIP"
    assert oggetti[0].role_id == 555


@pytest.mark.asyncio
async def test_add_item_senza_ruolo_e_facoltativo(repo):
    await repo.add_item(100, name="Badge decorativo", price=50)

    oggetti = await repo.list_items(100)
    assert oggetti[0].role_id is None


@pytest.mark.asyncio
async def test_list_items_ordinati_per_prezzo(repo):
    await repo.add_item(100, name="Caro", price=1000)
    await repo.add_item(100, name="Economico", price=10)

    oggetti = await repo.list_items(100)
    assert [o.name for o in oggetti] == ["Economico", "Caro"]


@pytest.mark.asyncio
async def test_remove_item(repo):
    item_id = await repo.add_item(100, name="X", price=10)

    rimosso = await repo.remove_item(item_id, guild_id=100)

    assert rimosso is True
    assert await repo.list_items(100) == []


@pytest.mark.asyncio
async def test_remove_item_altro_server_non_permesso(repo):
    item_id = await repo.add_item(100, name="X", price=10)

    assert await repo.remove_item(item_id, guild_id=999) is False


@pytest.mark.asyncio
async def test_get_item(repo):
    item_id = await repo.add_item(100, name="X", price=10)

    oggetto = await repo.get_item(item_id, guild_id=100)
    assert oggetto.name == "X"


@pytest.mark.asyncio
async def test_get_item_inesistente_restituisce_none(repo):
    assert await repo.get_item(99999, guild_id=100) is None


@pytest.mark.asyncio
async def test_record_purchase_e_has_purchased(repo):
    item_id = await repo.add_item(100, name="X", price=10)

    assert await repo.has_purchased(100, user_id=1, item_id=item_id) is False

    await repo.record_purchase(100, user_id=1, item_id=item_id)

    assert await repo.has_purchased(100, user_id=1, item_id=item_id) is True


@pytest.mark.asyncio
async def test_has_purchased_non_confonde_utenti_diversi(repo):
    item_id = await repo.add_item(100, name="X", price=10)
    await repo.record_purchase(100, user_id=1, item_id=item_id)

    assert await repo.has_purchased(100, user_id=2, item_id=item_id) is False
