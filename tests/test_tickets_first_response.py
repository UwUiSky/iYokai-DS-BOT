"""
tests/test_tickets_first_response.py
========================================
Test dell'on_message di TicketsCog che registra la prima risposta di
un operatore (SPEC.md §13.12) contro PostgreSQL reale — stesso
pattern di tests/test_moderation_shared_new_helpers.py.
"""

import discord
import pytest

from cogs.tickets.tickets import TicketsCog
from core.repositories.ticket_repo import ticket_repo


def _collega_pool_di_test(monkeypatch, clean_db) -> None:
    import core.database as database_module
    import core.repositories.ticket_repo as ticket_repo_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(ticket_repo_module.ticket_repo, "_pool_provider", lambda: clean_db)


class _FakeAuthor:
    def __init__(self, author_id: int, bot: bool = False) -> None:
        self.id = author_id
        self.bot = bot


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class _FakeMessage:
    def __init__(self, channel_id: int, author: _FakeAuthor, guild_id: int = 100) -> None:
        self.channel = _FakeChannel(channel_id)
        self.author = author
        self.guild = object() if guild_id is not None else None


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    _collega_pool_di_test(monkeypatch, clean_db)
    return clean_db


@pytest.mark.asyncio
async def test_messaggio_dello_staff_registra_la_prima_risposta():
    cog = TicketsCog(bot=None)
    await ticket_repo.create_ticket(100, user_id=1, channel_id=5001)

    await cog.on_message(_FakeMessage(5001, _FakeAuthor(2)))

    ticket = await ticket_repo.get_ticket_by_channel(5001)
    assert ticket.first_response_at is not None


@pytest.mark.asyncio
async def test_messaggio_dell_utente_non_registra_nulla():
    cog = TicketsCog(bot=None)
    await ticket_repo.create_ticket(100, user_id=1, channel_id=5001)

    await cog.on_message(_FakeMessage(5001, _FakeAuthor(1)))

    ticket = await ticket_repo.get_ticket_by_channel(5001)
    assert ticket.first_response_at is None


@pytest.mark.asyncio
async def test_messaggio_di_un_bot_non_registra_nulla():
    cog = TicketsCog(bot=None)
    await ticket_repo.create_ticket(100, user_id=1, channel_id=5001)

    await cog.on_message(_FakeMessage(5001, _FakeAuthor(2, bot=True)))

    ticket = await ticket_repo.get_ticket_by_channel(5001)
    assert ticket.first_response_at is None


@pytest.mark.asyncio
async def test_canale_non_ticket_non_solleva_eccezioni():
    cog = TicketsCog(bot=None)
    await cog.on_message(_FakeMessage(999999, _FakeAuthor(2)))  # non deve fallire


@pytest.mark.asyncio
async def test_seconda_risposta_non_sovrascrive_la_prima():
    cog = TicketsCog(bot=None)
    await ticket_repo.create_ticket(100, user_id=1, channel_id=5001)

    await cog.on_message(_FakeMessage(5001, _FakeAuthor(2)))
    ticket_dopo_prima = await ticket_repo.get_ticket_by_channel(5001)

    await cog.on_message(_FakeMessage(5001, _FakeAuthor(3)))
    ticket_dopo_seconda = await ticket_repo.get_ticket_by_channel(5001)

    assert ticket_dopo_prima.first_response_at == ticket_dopo_seconda.first_response_at
