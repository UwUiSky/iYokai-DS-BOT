"""
tests/test_music_inactive_handler.py
========================================
Test di core.music_fleet.handle_inactive_player() — la reazione
all'evento "wavelink_inactive_player" (SPEC.md §9.9, auto-leave su
canale vuoto). Il timeout stesso (300s di default) è gestito
internamente da wavelink/Lavalink, non testabile qui; questo è solo
il gestore che reagisce quando l'evento arriva.
"""

import pytest

from core.music_fleet import handle_inactive_player


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class _FakePlayer:
    def __init__(self, guild, channel=None, is_radio: bool = False) -> None:
        self.guild = guild
        self.channel = channel if channel is not None else _FakeChannel(555)
        if is_radio:
            self.is_radio = True
        self.disconnect_chiamato = False

    async def disconnect(self) -> None:
        self.disconnect_chiamato = True


class _FakeFleet:
    def __init__(self) -> None:
        self.release_session_chiamato_per: list[int] = []

    async def release_session(self, guild_id: int, channel_id: int = 0) -> None:
        self.release_session_chiamato_per.append(guild_id)


@pytest.mark.asyncio
async def test_disconnette_il_player_e_libera_il_worker_nella_flotta():
    player = _FakePlayer(guild=_FakeGuild(100))
    fleet = _FakeFleet()

    await handle_inactive_player(player, fleet)

    assert player.disconnect_chiamato is True
    assert fleet.release_session_chiamato_per == [100]


@pytest.mark.asyncio
async def test_player_senza_guild_disconnette_senza_toccare_la_flotta():
    player = _FakePlayer(guild=None)
    fleet = _FakeFleet()

    await handle_inactive_player(player, fleet)

    assert player.disconnect_chiamato is True
    assert fleet.release_session_chiamato_per == []


@pytest.mark.asyncio
async def test_libera_la_sessione_del_canale_del_player():
    """M 8.6: si rilascia la sessione di QUEL canale, non tutte quelle del server."""
    player = _FakePlayer(guild=_FakeGuild(100), channel=_FakeChannel(777))
    fleet = _FakeFleet()
    chiamate = []

    async def _release(guild_id, channel_id):
        chiamate.append((guild_id, channel_id))

    fleet.release_session = _release
    await handle_inactive_player(player, fleet)

    assert chiamate == [(100, 777)]


@pytest.mark.asyncio
async def test_la_radio_non_viene_scollegata_per_inattivita():
    """M 8.5 / LIM-44: l'evento "inattivo" non tocca la radio 24/7."""
    player = _FakePlayer(guild=_FakeGuild(100), is_radio=True)
    fleet = _FakeFleet()

    await handle_inactive_player(player, fleet)

    assert player.disconnect_chiamato is False
    assert fleet.release_session_chiamato_per == []
