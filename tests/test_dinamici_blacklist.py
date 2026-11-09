"""
tests/test_dinamici_blacklist.py
================================
SEC-10 per i bottoni dinamici nuovi di #128 (D69) e per BaseLayoutView: un utente in blacklist non passa.
Blacklist vera (clean_db), come fa `/owner blacklist`.
"""

import discord
import pytest

from cogs.utility.embed_avanzati import BottoneTag
from cogs.utility.reminders import BottoneRicordaAnche
from cogs.utility.strumenti_rapidi import BottoneCronometro
from cogs.utility.suggestions import BottoneChiScrisse
from core.repositories.blacklist_repo import blacklist_repo
from core.ui_base import BaseLayoutView
from tests.support.discord_fakes import fake_interaction

ELEMENTI = [
    lambda: BottoneTag(1, "avviso", 0),
    lambda: BottoneRicordaAnche("abcdef"),
    lambda: BottoneCronometro("giro", 1),
    lambda: BottoneChiScrisse(1),
    lambda: BaseLayoutView(timeout=None),
]


@pytest.fixture
async def db_collegato(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    blacklist_repo._user_cache.clear()
    blacklist_repo._guild_cache.clear() if hasattr(blacklist_repo, "_guild_cache") else None
    return clean_db


@pytest.mark.parametrize("crea", ELEMENTI)
async def test_utente_in_blacklist_e_fermato(crea, db_collegato):
    interaction = fake_interaction()
    await blacklist_repo.add_user(interaction.user.id, "test", added_by=1)
    assert await crea().interaction_check(interaction) is False


@pytest.mark.parametrize("crea", ELEMENTI)
async def test_utente_normale_passa(crea, db_collegato):
    assert await crea().interaction_check(fake_interaction()) is True
