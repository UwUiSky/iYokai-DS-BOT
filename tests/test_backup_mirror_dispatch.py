"""
tests/test_backup_mirror_dispatch.py
========================================
Test di BackupMirrorDispatcher (SPEC.md §11.9) — nessuna vera
chiamata di rete: _send() viene sostituita da una finta che registra
le chiamate invece di contattare Discord.
"""

import pytest

from core.backup_mirror_dispatch import BackupMirrorDispatcher
from core.backup_mirror_logic import MirrorRateLimiter


class _FakeAuthor:
    def __init__(self, bot: bool = False) -> None:
        self.bot = bot
        self.display_name = "Utente Finto"


class _FakeGuild:
    id = 100


class _FakeMessage:
    def __init__(self, channel_id: int, author=None, guild=_FakeGuild(), content: str = "ciao"):
        self.channel = type("_Canale", (), {"id": channel_id})()
        self.author = author or _FakeAuthor()
        self.guild = guild
        self.content = content
        self.attachments = []


class _FakeMirrorRepo:
    def __init__(self, mapping: dict[int, str]) -> None:
        self._mapping = mapping

    async def get_webhook_url(self, channel_id: int) -> str | None:
        return self._mapping.get(channel_id)


class _DispatcherRegistraChiamate(BackupMirrorDispatcher):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.chiamate_send: list[tuple] = []

    async def _send(self, webhook_url: str, message) -> None:
        self.chiamate_send.append((webhook_url, message))


@pytest.mark.asyncio
async def test_messaggio_su_canale_mappato_viene_inoltrato():
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)

    inoltrato = await dispatcher.handle_message(_FakeMessage(channel_id=10))

    assert inoltrato is True
    assert dispatcher.chiamate_send[0][0] == "https://discord.com/api/webhooks/abc"


@pytest.mark.asyncio
async def test_canale_non_mappato_non_viene_inoltrato():
    repo = _FakeMirrorRepo({})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)

    inoltrato = await dispatcher.handle_message(_FakeMessage(channel_id=999))

    assert inoltrato is False
    assert dispatcher.chiamate_send == []


@pytest.mark.asyncio
async def test_messaggio_di_un_bot_non_viene_inoltrato():
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)

    messaggio = _FakeMessage(channel_id=10, author=_FakeAuthor(bot=True))
    inoltrato = await dispatcher.handle_message(messaggio)

    assert inoltrato is False


@pytest.mark.asyncio
async def test_messaggio_in_dm_non_viene_inoltrato():
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo)

    messaggio = _FakeMessage(channel_id=10, guild=None)
    inoltrato = await dispatcher.handle_message(messaggio)

    assert inoltrato is False


@pytest.mark.asyncio
async def test_rate_limit_scarta_il_burst_oltre_5_messaggi_in_5s():
    repo = _FakeMirrorRepo({10: "https://discord.com/api/webhooks/abc"})
    limiter = MirrorRateLimiter(max_messages=5, window_seconds=5.0)
    dispatcher = _DispatcherRegistraChiamate(mirror_repo=repo, rate_limiter=limiter)

    risultati = [await dispatcher.handle_message(_FakeMessage(channel_id=10)) for _ in range(6)]

    assert risultati == [True, True, True, True, True, False]
    assert len(dispatcher.chiamate_send) == 5
