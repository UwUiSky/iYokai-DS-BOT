"""
tests/test_advanced_logs_router.py
==================================
Log avanzati con il router (NF-01): canali offuscati ignorati (M 5.8),
spostamenti di canale in un solo messaggio e mute proprio distinto da
quello del server (M 5.6), tipo «voce» e «server».
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.logging.advanced_logs as modulo
from core.channel_router import TIPO_SERVER, TIPO_VOCE
from core.logging_advanced_logic import classify_voice_state_change
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel


@pytest.fixture
def cog(monkeypatch):
    monkeypatch.setattr(modulo, "logging_avanzato_attivo", AsyncMock(return_value=True))
    monkeypatch.setattr(modulo.event_log_repo, "log_event", AsyncMock())
    invio = AsyncMock()
    monkeypatch.setattr(modulo, "send_event_embed", invio)
    monkeypatch.setattr(modulo, "SPOSTAMENTI_ATTESA_SECONDI", 0)
    return modulo.AdvancedLogsCog(bot=MagicMock()), invio


def _canale(cid, nome="chat", posizione=0, server=None):
    c = fake_text_channel(cid, name=nome)
    c.guild = server or fake_guild(guild_id=77)
    c.category_id, c.topic, c.nsfw, c.slowmode_delay, c.position = None, None, False, 0, posizione
    return c


async def test_canale_offuscato_non_genera_nessun_log(cog):
    c, invio = cog
    nascosto = _canale(1, nome="___hidden___")
    visibile = _canale(1, nome="chat")
    await c.on_guild_channel_create(nascosto)
    await c.on_guild_channel_delete(nascosto)
    await c.on_guild_channel_update(visibile, nascosto)
    await c.on_guild_channel_update(nascosto, visibile)
    invio.assert_not_awaited()
    modulo.event_log_repo.log_event.assert_not_awaited()


async def test_dieci_spostamenti_insieme_un_solo_messaggio(cog):
    c, invio = cog
    server = fake_guild(guild_id=77)
    for n in range(10):
        await c.on_guild_channel_update(_canale(n, posizione=n, server=server), _canale(n, posizione=n + 1, server=server))
    await asyncio.gather(*list(c._invii_spostamenti))
    invio.assert_awaited_once()
    guild, tipo, testo = invio.await_args.args
    assert tipo == "channel_move" and "10" in testo
    assert modulo.event_log_repo.log_event.await_count == 10  # nel database restano tutti


async def test_spostamento_insieme_a_un_altro_cambio_resta_un_messaggio_normale(cog):
    c, invio = cog
    server = fake_guild(guild_id=77)
    prima = _canale(1, nome="a", posizione=1, server=server)
    dopo = _canale(1, nome="b", posizione=2, server=server)
    await c.on_guild_channel_update(prima, dopo)
    assert invio.await_args.args[1] == "channel_update"
    assert not c._invii_spostamenti


def _stato(canale=None, **flag):
    s = MagicMock()
    s.channel = canale
    s.mute = s.deaf = s.self_mute = s.self_deaf = False
    for k, v in flag.items():
        setattr(s, k, v)
    return s


def test_mute_proprio_e_mute_del_server_sono_due_eventi_diversi():
    base = {"channel_id": 1, "mute": False, "deaf": False, "self_mute": False, "self_deaf": False}
    assert classify_voice_state_change(base, {**base, "self_mute": True}) == ["voice_self_mute"]
    assert classify_voice_state_change(base, {**base, "mute": True}) == ["voice_mute"]
    assert classify_voice_state_change({**base, "self_deaf": True}, base) == ["voice_self_undeafen"]
    assert "Server" not in modulo.EVENT_TITLES["voice_self_mute"][0]


async def test_il_listener_vocale_usa_gli_stati_separati(cog):
    c, invio = cog
    canale = fake_text_channel(5)
    membro = fake_member(user_id=9)
    membro.guild = fake_guild(guild_id=77)
    await c.on_voice_state_update(membro, _stato(canale), _stato(canale, self_mute=True))
    assert invio.await_args.args[1] == "voice_self_mute"


async def test_tipo_di_destinazione_voce_e_server(monkeypatch):
    visti = []

    async def finta(guild, tipo):
        visti.append(tipo)
        return None

    monkeypatch.setattr(modulo, "advanced_log_channel", finta)
    server = fake_guild(guild_id=77)
    await modulo.send_event_embed(server, "voice_join", "x")
    await modulo.send_event_embed(server, "role_edit", "x")
    assert visti == [TIPO_VOCE, TIPO_SERVER]


async def test_descrizione_lunga_resta_entro_4096(monkeypatch):
    canale = AsyncMock()
    canale.id = 1
    monkeypatch.setattr(modulo, "advanced_log_channel", AsyncMock(return_value=canale))
    inviato = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo.router, "invia_a", inviato)
    await modulo.send_event_embed(fake_guild(guild_id=77), "channel_move", "x" * 9000)
    assert len(inviato.await_args.kwargs["embed"].description) <= 4096
