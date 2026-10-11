"""
tests/test_soundboard_log_service.py
====================================
Log del soundboard (SPEC §8.13): arriva dagli eventi gateway di
discord.py, senza giro periodico sull'audit log (M 5.7, LIM-31).
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.logging.advanced_logs as modulo
from tests.support.discord_fakes import fake_guild


@pytest.fixture
def cog(monkeypatch):
    monkeypatch.setattr(modulo, "logging_avanzato_attivo", AsyncMock(return_value=True))
    log_event = AsyncMock()
    monkeypatch.setattr(modulo.event_log_repo, "log_event", log_event)
    invio = AsyncMock()
    monkeypatch.setattr(modulo, "send_event_embed", invio)
    return modulo.AdvancedLogsCog(bot=MagicMock()), log_event, invio


def _suono(nome="boom", user_id=7):
    suono = MagicMock()
    suono.name = nome
    suono.guild = fake_guild(guild_id=321)
    suono.user = MagicMock(id=user_id) if user_id else None
    return suono


async def test_suono_creato_una_riga_di_log_con_chi_lo_ha_creato(cog):
    c, log_event, invio = cog
    await c.on_soundboard_sound_create(_suono())
    log_event.assert_awaited_once()
    assert log_event.await_args.args[:2] == (321, "soundboard_sound_create")
    assert log_event.await_args.kwargs["actor_id"] == 7
    assert invio.await_args.args[1] == "soundboard_sound_create"
    assert "boom" in invio.await_args.args[2] and "<@7>" in invio.await_args.args[2]


async def test_suono_modificato_e_cancellato(cog):
    c, log_event, invio = cog
    await c.on_soundboard_sound_update(_suono("vecchio"), _suono("nuovo"))
    await c.on_soundboard_sound_delete(_suono("nuovo", user_id=None))
    assert [call.args[1] for call in log_event.await_args_list] == [
        "soundboard_sound_update", "soundboard_sound_delete",
    ]
    assert log_event.await_args_list[0].kwargs["details"] == {"name": "nuovo"}


async def test_senza_logging_avanzato_il_suono_non_viene_registrato(cog, monkeypatch):
    c, log_event, invio = cog
    monkeypatch.setattr(modulo, "logging_avanzato_attivo", AsyncMock(return_value=False))
    await c.on_soundboard_sound_create(_suono())
    log_event.assert_not_awaited()
    invio.assert_not_awaited()


def test_gli_eventi_esistono_in_discord_py():
    sorgente = open(discord.state.__file__, encoding="utf-8").read()
    for nome in ("soundboard_sound_create", "soundboard_sound_update", "soundboard_sound_delete"):
        assert f"self.dispatch('{nome}'" in sorgente
