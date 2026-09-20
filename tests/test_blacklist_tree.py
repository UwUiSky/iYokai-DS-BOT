"""
tests/test_blacklist_tree.py
===============================
Test di BlacklistAwareCommandTree.interaction_check() — il
comportamento reale (blocca utenti/server in blacklist, lascia
passare tutto il resto), contro PostgreSQL vero, non un mock.
"""

import discord
import pytest
from discord.ext import commands

from core.blacklist_tree import BlacklistAwareCommandTree
from core.repositories.blacklist_repo import BlacklistRepository
import core.blacklist_tree as blacklist_tree_module


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append(content)


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeInteraction:
    def __init__(self, user_id: int, guild_id: int | None) -> None:
        self.user = _FakeUser(user_id)
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.response = _FakeResponse()


def _collega(monkeypatch, clean_db):
    monkeypatch.setattr(
        blacklist_tree_module,
        "blacklist_repo",
        BlacklistRepository(pool_provider=lambda: clean_db),
    )


@pytest.mark.asyncio
async def test_utente_non_bloccato_passa(monkeypatch, clean_db):
    _collega(monkeypatch, clean_db)
    bot = commands.Bot(
        command_prefix="!", intents=discord.Intents.default(), tree_cls=BlacklistAwareCommandTree
    )

    interaction = _FakeInteraction(user_id=1, guild_id=100)
    assert await bot.tree.interaction_check(interaction) is True
    assert interaction.response.sent_messages == []


@pytest.mark.asyncio
async def test_utente_bloccato_viene_fermato(monkeypatch, clean_db):
    _collega(monkeypatch, clean_db)
    repo = blacklist_tree_module.blacklist_repo
    await repo.add_user(1, reason="test", added_by=99)

    bot = commands.Bot(
        command_prefix="!", intents=discord.Intents.default(), tree_cls=BlacklistAwareCommandTree
    )

    interaction = _FakeInteraction(user_id=1, guild_id=100)
    risultato = await bot.tree.interaction_check(interaction)

    assert risultato is False
    assert len(interaction.response.sent_messages) == 1


@pytest.mark.asyncio
async def test_server_bloccato_viene_fermato_senza_risposta(monkeypatch, clean_db):
    _collega(monkeypatch, clean_db)
    repo = blacklist_tree_module.blacklist_repo
    await repo.add_guild(100, reason="test", added_by=99)

    bot = commands.Bot(
        command_prefix="!", intents=discord.Intents.default(), tree_cls=BlacklistAwareCommandTree
    )

    interaction = _FakeInteraction(user_id=1, guild_id=100)
    risultato = await bot.tree.interaction_check(interaction)

    assert risultato is False
    # Nessuna risposta per un server bloccato, a differenza
    # dell'utente bloccato — per progetto, non un dettaglio casuale.
    assert interaction.response.sent_messages == []


@pytest.mark.asyncio
async def test_interazione_in_dm_senza_guild_non_solleva(monkeypatch, clean_db):
    _collega(monkeypatch, clean_db)
    bot = commands.Bot(
        command_prefix="!", intents=discord.Intents.default(), tree_cls=BlacklistAwareCommandTree
    )

    interaction = _FakeInteraction(user_id=1, guild_id=None)
    assert await bot.tree.interaction_check(interaction) is True


@pytest.mark.asyncio
async def test_interazione_passata_incrementa_il_contatore_comandi(monkeypatch, clean_db):
    import core.bot_stats as bot_stats_module

    _collega(monkeypatch, clean_db)
    monkeypatch.setattr(blacklist_tree_module, "command_counter", bot_stats_module.RollingCounter())

    bot = commands.Bot(
        command_prefix="!", intents=discord.Intents.default(), tree_cls=BlacklistAwareCommandTree
    )

    interaction = _FakeInteraction(user_id=1, guild_id=100)
    await bot.tree.interaction_check(interaction)

    assert blacklist_tree_module.command_counter.count_in_window() == 1


@pytest.mark.asyncio
async def test_interazione_bloccata_non_incrementa_il_contatore(monkeypatch, clean_db):
    import core.bot_stats as bot_stats_module

    _collega(monkeypatch, clean_db)
    monkeypatch.setattr(blacklist_tree_module, "command_counter", bot_stats_module.RollingCounter())
    repo = blacklist_tree_module.blacklist_repo
    await repo.add_user(1, reason="test", added_by=99)

    bot = commands.Bot(
        command_prefix="!", intents=discord.Intents.default(), tree_cls=BlacklistAwareCommandTree
    )

    interaction = _FakeInteraction(user_id=1, guild_id=100)
    await bot.tree.interaction_check(interaction)

    assert blacklist_tree_module.command_counter.count_in_window() == 0
