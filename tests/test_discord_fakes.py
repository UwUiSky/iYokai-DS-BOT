"""
tests/test_discord_fakes.py
===============================
Dimostra che ogni finto di tests/support/discord_fakes.py rifiuta una
chiamata con una firma sbagliata (autospec), a differenza di un finto
scritto a mano che accetterebbe qualunque argomento.
Funzioni coperte: metodo RT-1 di PIANO_FIX.md.
"""

from __future__ import annotations

import pytest

from tests.support.discord_fakes import (
    fake_forum_channel,
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
    fake_voice_channel,
)


def test_text_channel_rifiuta_delay_su_delete():
    """BUG-1 reale: TextChannel.delete() non ha un parametro 'delay'."""
    canale = fake_text_channel()
    with pytest.raises(TypeError):
        canale.delete(delay=10)


@pytest.mark.asyncio
async def test_text_channel_delete_vera_firma_e_awaitable():
    canale = fake_text_channel()
    await canale.delete(reason="test")
    canale.delete.assert_awaited_once_with(reason="test")


def test_text_channel_send_rifiuta_argomento_inesistente():
    canale = fake_text_channel()
    with pytest.raises(TypeError):
        canale.send(testo="ciao")  # il parametro vero si chiama 'content'


def test_voice_channel_ha_id_e_type_coerenti():
    canale = fake_voice_channel(channel_id=42, name="Sala 1")
    assert canale.id == 42
    assert canale.name == "Sala 1"


def test_forum_channel_rifiuta_metodo_inesistente():
    canale = fake_forum_channel()
    with pytest.raises(AttributeError):
        canale.metodo_che_non_esiste()


def test_role_rifiuta_argomento_inesistente_su_edit():
    ruolo = fake_role(role_id=1, name="Admin")
    with pytest.raises(TypeError):
        ruolo.edit(colore="rosso")  # il parametro vero si chiama 'colour'/'color'


def test_member_ban_rifiuta_parametro_inesistente():
    membro = fake_member()
    with pytest.raises(TypeError):
        membro.ban(motivo="test")  # il parametro vero si chiama 'reason'


def test_guild_costruita_con_owner_e_me():
    server = fake_guild(guild_id=1, owner_id=2)
    assert server.id == 1
    assert server.owner_id == 2
    assert server.me.bot is True


def test_message_ha_author_channel_guild_di_default():
    messaggio = fake_message(content="ciao")
    assert messaggio.content == "ciao"
    assert messaggio.author is not None
    assert messaggio.channel is not None
    assert messaggio.guild is not None


@pytest.mark.asyncio
async def test_interaction_response_send_message_e_awaitable_e_tracciabile():
    interazione = fake_interaction()
    assert interazione.response.is_done() is False
    await interazione.response.send_message("ciao", ephemeral=True)
    interazione.response.send_message.assert_awaited_once_with("ciao", ephemeral=True)


def test_interaction_response_send_message_rifiuta_argomento_inesistente():
    interazione = fake_interaction()
    with pytest.raises(TypeError):
        interazione.response.send_message(testo="ciao")


@pytest.mark.asyncio
async def test_interaction_followup_send_e_awaitable():
    interazione = fake_interaction()
    await interazione.followup.send("ok")
    interazione.followup.send.assert_awaited_once()
