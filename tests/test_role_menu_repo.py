"""
tests/test_role_menu_repo.py
===============================
Test di RoleMenuRepository contro PostgreSQL reale.
"""

import pytest

from core.repositories.role_menu_repo import RoleMenuRepository


@pytest.fixture
def repo(clean_db):
    return RoleMenuRepository(pool_provider=lambda: clean_db)


# ====================================================================
# Menu
# ====================================================================
@pytest.mark.asyncio
async def test_create_e_get_menu(repo):
    menu_id = await repo.create_menu(
        guild_id=100,
        channel_id=200,
        mode="button",
        toggle=True,
        max_selectable=None,
        title="Scegli i tuoi ruoli",
        description="Clicca per ottenere un ruolo",
    )
    menu = await repo.get_menu(menu_id)
    assert menu is not None
    assert menu.guild_id == 100
    assert menu.mode == "button"
    assert menu.message_id is None


@pytest.mark.asyncio
async def test_get_menu_inesistente_restituisce_none(repo):
    assert await repo.get_menu(999999) is None


@pytest.mark.asyncio
async def test_set_menu_message(repo):
    menu_id = await repo.create_menu(100, 200, "reaction", True, None, "T", "")
    await repo.set_menu_message(menu_id, message_id=555)

    menu = await repo.get_menu(menu_id)
    assert menu.message_id == 555


@pytest.mark.asyncio
async def test_get_menu_by_message(repo):
    menu_id = await repo.create_menu(100, 200, "select", False, 2, "T", "")
    await repo.set_menu_message(menu_id, message_id=555)

    menu = await repo.get_menu_by_message(100, 555)
    assert menu is not None
    assert menu.id == menu_id


@pytest.mark.asyncio
async def test_get_menu_by_message_server_sbagliato_non_trova(repo):
    menu_id = await repo.create_menu(100, 200, "select", False, 2, "T", "")
    await repo.set_menu_message(menu_id, message_id=555)

    assert await repo.get_menu_by_message(999, 555) is None


@pytest.mark.asyncio
async def test_list_menus_by_mode_filtra_correttamente(repo):
    id1 = await repo.create_menu(100, 200, "button", True, None, "A", "")
    await repo.set_menu_message(id1, 1)
    id2 = await repo.create_menu(100, 200, "select", True, None, "B", "")
    await repo.set_menu_message(id2, 2)
    id3 = await repo.create_menu(100, 200, "button", True, None, "C", "")
    await repo.set_menu_message(id3, 3)

    menu_bottone = await repo.list_menus_by_mode("button")
    assert {m.id for m in menu_bottone} == {id1, id3}


@pytest.mark.asyncio
async def test_list_menus_by_mode_esclude_menu_senza_messaggio(repo):
    # Un menu creato ma non ancora pubblicato (message_id NULL) non
    # deve comparire: non c'è nessun messaggio a cui agganciare una
    # View all'avvio del bot.
    await repo.create_menu(100, 200, "button", True, None, "Non pubblicato", "")

    menu_bottone = await repo.list_menus_by_mode("button")
    assert menu_bottone == []


@pytest.mark.asyncio
async def test_delete_menu(repo):
    menu_id = await repo.create_menu(100, 200, "button", True, None, "T", "")
    await repo.delete_menu(menu_id)
    assert await repo.get_menu(menu_id) is None


@pytest.mark.asyncio
async def test_delete_menu_elimina_anche_le_opzioni(repo):
    # ON DELETE CASCADE sulla foreign key.
    menu_id = await repo.create_menu(100, 200, "button", True, None, "T", "")
    await repo.add_option(menu_id, role_id=1, emoji=None, label="Opzione 1")

    await repo.delete_menu(menu_id)

    opzioni = await repo.get_options(menu_id)
    assert opzioni == []


# ====================================================================
# Opzioni
# ====================================================================
@pytest.mark.asyncio
async def test_add_option_e_get_options(repo):
    menu_id = await repo.create_menu(100, 200, "reaction", True, None, "T", "")
    await repo.add_option(menu_id, role_id=1, emoji="🎮", label=None)

    opzioni = await repo.get_options(menu_id)
    assert len(opzioni) == 1
    assert opzioni[0].role_id == 1
    assert opzioni[0].emoji == "🎮"


@pytest.mark.asyncio
async def test_add_option_assegna_posizioni_progressive(repo):
    menu_id = await repo.create_menu(100, 200, "button", True, None, "T", "")
    await repo.add_option(menu_id, role_id=1, emoji=None, label="Prima")
    await repo.add_option(menu_id, role_id=2, emoji=None, label="Seconda")
    await repo.add_option(menu_id, role_id=3, emoji=None, label="Terza")

    opzioni = await repo.get_options(menu_id)
    assert [o.position for o in opzioni] == [0, 1, 2]
    assert [o.label for o in opzioni] == ["Prima", "Seconda", "Terza"]


@pytest.mark.asyncio
async def test_add_option_stesso_ruolo_due_volte_aggiorna_invece_di_duplicare(repo):
    menu_id = await repo.create_menu(100, 200, "button", True, None, "T", "")
    await repo.add_option(menu_id, role_id=1, emoji=None, label="Prima etichetta")
    await repo.add_option(menu_id, role_id=1, emoji=None, label="Etichetta aggiornata")

    opzioni = await repo.get_options(menu_id)
    assert len(opzioni) == 1
    assert opzioni[0].label == "Etichetta aggiornata"


@pytest.mark.asyncio
async def test_remove_option(repo):
    menu_id = await repo.create_menu(100, 200, "button", True, None, "T", "")
    await repo.add_option(menu_id, role_id=1, emoji=None, label="X")

    rimosso = await repo.remove_option(menu_id, role_id=1)
    assert rimosso is True
    assert await repo.get_options(menu_id) == []


@pytest.mark.asyncio
async def test_remove_option_inesistente_restituisce_false(repo):
    menu_id = await repo.create_menu(100, 200, "button", True, None, "T", "")
    rimosso = await repo.remove_option(menu_id, role_id=999)
    assert rimosso is False


@pytest.mark.asyncio
async def test_count_options(repo):
    menu_id = await repo.create_menu(100, 200, "button", True, None, "T", "")
    assert await repo.count_options(menu_id) == 0

    await repo.add_option(menu_id, role_id=1, emoji=None, label="X")
    await repo.add_option(menu_id, role_id=2, emoji=None, label="Y")
    assert await repo.count_options(menu_id) == 2


@pytest.mark.asyncio
async def test_get_option_by_emoji(repo):
    menu_id = await repo.create_menu(100, 200, "reaction", True, None, "T", "")
    await repo.add_option(menu_id, role_id=1, emoji="🎮", label=None)
    await repo.add_option(menu_id, role_id=2, emoji="🎨", label=None)

    trovata = await repo.get_option_by_emoji(menu_id, "🎨")
    assert trovata is not None
    assert trovata.role_id == 2


@pytest.mark.asyncio
async def test_get_option_by_emoji_non_trovata(repo):
    menu_id = await repo.create_menu(100, 200, "reaction", True, None, "T", "")
    assert await repo.get_option_by_emoji(menu_id, "🎮") is None


@pytest.mark.asyncio
async def test_opzioni_non_mischiano_menu_diversi(repo):
    menu1 = await repo.create_menu(100, 200, "button", True, None, "A", "")
    menu2 = await repo.create_menu(100, 200, "button", True, None, "B", "")
    await repo.add_option(menu1, role_id=1, emoji=None, label="Solo menu 1")

    assert len(await repo.get_options(menu1)) == 1
    assert len(await repo.get_options(menu2)) == 0
