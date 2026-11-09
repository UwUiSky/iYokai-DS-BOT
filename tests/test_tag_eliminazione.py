"""Un tag eliminato porta via errori, inneschi, comandi e menu del server; poi albero e sync."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import tag_eliminazione as T
from core.repositories.slash_server_repo import SlashServerRepository

G = 777


@pytest.fixture
def repo(clean_db):
    return SlashServerRepository(pool_provider=lambda: clean_db)


async def test_repo_toglie_comandi_e_menu_del_tag(repo):
    await repo.pubblica(G, "regole", "", "regole", "d", 1)
    await repo.pubblica(G, "altro", "", "altro", "d", 1)
    await repo.aggiungi_menu(G, "Menu", "utente", "regole", 1)
    assert await repo.togli_per_tag(G, "regole") == 2
    assert [r["nome"] for r in await repo.comandi(G)] == ["altro"]
    assert await repo.menu(G) == []


async def test_pulizia_unica_rimonta_e_sincronizza(monkeypatch):
    errori, inneschi, slash = AsyncMock(), AsyncMock(), AsyncMock(return_value=1)
    monkeypatch.setattr(T.tag_script_repo, "togli_errori", errori)
    monkeypatch.setattr(T.tag_inneschi_repo, "togli_per_tag", inneschi)
    monkeypatch.setattr(T.slash_server_repo, "togli_per_tag", slash)
    cog = MagicMock()
    cog.dopo_tag_eliminato = AsyncMock()
    bot = MagicMock()
    bot.get_cog.return_value = cog
    await T.pulisci_tag_eliminato(bot, G, "regole")
    errori.assert_awaited_once_with(G, "regole")
    inneschi.assert_awaited_once_with(G, "regole")
    slash.assert_awaited_once_with(G, "regole")
    cog.dopo_tag_eliminato.assert_awaited_once_with(G)


async def test_senza_comandi_del_server_non_sincronizza(monkeypatch):
    for r in (T.tag_script_repo, T.tag_inneschi_repo):
        for n in ("togli_errori", "togli_per_tag"):
            if hasattr(r, n):
                monkeypatch.setattr(r, n, AsyncMock())
    monkeypatch.setattr(T.slash_server_repo, "togli_per_tag", AsyncMock(return_value=0))
    cog = MagicMock()
    cog.dopo_tag_eliminato = AsyncMock()
    bot = MagicMock()
    bot.get_cog.return_value = cog
    await T.pulisci_tag_eliminato(bot, G, "regole")
    cog.dopo_tag_eliminato.assert_not_awaited()
