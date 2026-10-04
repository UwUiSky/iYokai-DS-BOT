"""
tests/test_voice_temp_transfer.py
=================================
/voice transfer (BUG-18, prima metà): la proprietà di un canale
vocale temporaneo passa solo a una persona che è dentro quel canale.
Un bot o un utente assente vengono rifiutati.
"""

from unittest.mock import create_autospec

import discord
import pytest

import cogs.voice_temp.voice_temp as modulo
from core.repositories.voice_temp_repo import VoiceTempRepository
from tests.support.discord_fakes import fake_interaction, fake_member, fake_voice_channel

ID_PROPRIETARIO = 10


def _in_vocale(membro, canale):
    """Mette il membro nel canale vocale indicato (None = non connesso)."""
    if canale is None:
        membro.voice = None
    else:
        membro.voice = create_autospec(discord.VoiceState, instance=True)
        membro.voice.channel = canale
    return membro


@pytest.fixture
def repo_finto(monkeypatch):
    finto = create_autospec(VoiceTempRepository, instance=True)
    finto.get_owner.return_value = ID_PROPRIETARIO
    monkeypatch.setattr(modulo, "voice_temp_repo", finto)
    return finto


@pytest.fixture
def canale():
    return fake_voice_channel(channel_id=222)


@pytest.fixture
def interazione(canale):
    proprietario = _in_vocale(fake_member(user_id=ID_PROPRIETARIO), canale)
    return fake_interaction(user=proprietario)


async def _trasferisci(interazione, destinatario) -> None:
    cog = modulo.VoiceTempCog(bot=None)
    await cog.transfer.callback(cog, interazione, destinatario)


async def test_transfer_a_un_bot_viene_rifiutato(repo_finto, canale, interazione):
    destinatario = _in_vocale(fake_member(user_id=20, bot=True), canale)

    await _trasferisci(interazione, destinatario)

    repo_finto.set_owner.assert_not_awaited()
    risposta = interazione.response.send_message.call_args
    assert "bot" in risposta.args[0]
    assert risposta.kwargs["ephemeral"] is True


async def test_transfer_a_chi_non_e_in_vocale_viene_rifiutato(repo_finto, interazione):
    destinatario = _in_vocale(fake_member(user_id=20), None)

    await _trasferisci(interazione, destinatario)

    repo_finto.set_owner.assert_not_awaited()
    risposta = interazione.response.send_message.call_args
    assert "non è nel canale" in risposta.args[0]
    assert risposta.kwargs["ephemeral"] is True


async def test_transfer_a_chi_e_in_un_altro_vocale_viene_rifiutato(repo_finto, interazione):
    destinatario = _in_vocale(fake_member(user_id=20), fake_voice_channel(channel_id=333))

    await _trasferisci(interazione, destinatario)

    repo_finto.set_owner.assert_not_awaited()


async def test_transfer_a_una_persona_nel_canale_riesce(repo_finto, canale, interazione):
    destinatario = _in_vocale(fake_member(user_id=20), canale)

    await _trasferisci(interazione, destinatario)

    repo_finto.set_owner.assert_awaited_once_with(222, 20)
