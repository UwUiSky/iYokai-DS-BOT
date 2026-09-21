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


class _FakePlayer:
    def __init__(self, guild) -> None:
        self.guild = guild
        self.disconnect_chiamato = False

    async def disconnect(self) -> None:
        self.disconnect_chiamato = True


class _FakeFleet:
    def __init__(self) -> None:
        self.release_guild_chiamato_per: list[int] = []

    async def release_guild(self, guild_id: int) -> None:
        self.release_guild_chiamato_per.append(guild_id)


@pytest.mark.asyncio
async def test_disconnette_il_player_e_libera_il_worker_nella_flotta():
    player = _FakePlayer(guild=_FakeGuild(100))
    fleet = _FakeFleet()

    await handle_inactive_player(player, fleet)

    assert player.disconnect_chiamato is True
    assert fleet.release_guild_chiamato_per == [100]


@pytest.mark.asyncio
async def test_player_senza_guild_disconnette_senza_toccare_la_flotta():
    player = _FakePlayer(guild=None)
    fleet = _FakeFleet()

    await handle_inactive_player(player, fleet)

    assert player.disconnect_chiamato is True
    assert fleet.release_guild_chiamato_per == []
