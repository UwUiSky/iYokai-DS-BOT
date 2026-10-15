"""
tests/test_bot_roles.py
=======================
iYokai Mod (D15): un solo punto sceglie chi esegue log e azioni; un'azione
la fa un bot solo; senza Mod, o se Mod non può, fa tutto il principale.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.channel_router as router
from core import bot_roles
from core.mod_bot import ModBot
from tests.support.discord_fakes import fake_guild, fake_member, fake_role, fake_text_channel
from tests.support.router_fakes import router_senza_scelte

GUILD_ID = 900


@pytest.fixture(autouse=True)
def senza_mod():
    bot_roles.registra_mod(None)
    yield
    bot_roles.registra_mod(None)


def _mod(permessi: discord.Permissions | None = None, posizione: int = 10, pronto: bool = True):
    """Un client Mod collegato, presente nel server GUILD_ID."""
    io = fake_member(user_id=4242, bot=True, roles=[fake_role(role_id=77, position=posizione)])
    io.guild_permissions = permessi if permessi is not None else discord.Permissions.all()
    server = fake_guild(guild_id=GUILD_ID, me=io)
    client = MagicMock(spec=discord.Client)
    client.is_ready.return_value = pronto
    client.is_closed.return_value = False
    client.get_guild.side_effect = lambda gid: server if gid == GUILD_ID else None
    client.user = io
    client.http = MagicMock()
    for nome in ("ban", "unban", "kick", "edit_member", "add_role", "delete_message", "delete_messages"):
        setattr(client.http, nome, AsyncMock())
    bot_roles.registra_mod(client)
    return client, server


def _principale():
    return fake_guild(guild_id=GUILD_ID)


@pytest.mark.asyncio
async def test_senza_mod_agisce_il_principale():
    guild = _principale()
    membro = fake_member(user_id=5)
    membro.guild = guild
    await bot_roles.espelli(membro, reason="x")
    membro.kick.assert_awaited_once_with(reason="x")


@pytest.mark.asyncio
async def test_con_mod_l_azione_la_fa_solo_mod():
    client, _ = _mod()
    guild = _principale()
    membro = fake_member(user_id=5)
    membro.guild = guild
    await bot_roles.banna(guild, membro, reason="raid", delete_message_seconds=0)
    client.http.ban.assert_awaited_once_with(5, GUILD_ID, 0, reason="raid")
    guild.ban.assert_not_awaited()
    membro.ban.assert_not_awaited()


@pytest.mark.asyncio
async def test_mod_non_collegato_agisce_il_principale():
    client, _ = _mod(pronto=False)
    guild = _principale()
    await bot_roles.sbanna(guild, discord.Object(id=5), reason="fine")
    guild.unban.assert_awaited_once()
    client.http.unban.assert_not_awaited()


@pytest.mark.asyncio
async def test_mod_senza_permesso_agisce_il_principale():
    client, _ = _mod(permessi=discord.Permissions(kick_members=True))
    guild = _principale()
    await bot_roles.sbanna(guild, discord.Object(id=5), reason="fine")
    guild.unban.assert_awaited_once()
    client.http.unban.assert_not_awaited()


@pytest.mark.asyncio
async def test_mod_sotto_il_bersaglio_agisce_il_principale():
    client, _ = _mod(posizione=3)
    guild = _principale()
    membro = fake_member(user_id=5, roles=[fake_role(role_id=8, position=5)])
    membro.guild = guild
    await bot_roles.isola(membro, timedelta(minutes=5), reason="spam")
    membro.timeout.assert_awaited_once()
    client.http.edit_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_rate_limit_lungo_passa_al_principale_e_ferma_mod():
    client, _ = _mod()
    client.http.kick.side_effect = discord.RateLimited(120.0)
    guild = _principale()
    membro = fake_member(user_id=5)
    membro.guild = guild
    await bot_roles.espelli(membro, reason="x")
    membro.kick.assert_awaited_once()
    # Fermo: la prossima azione non prova nemmeno Mod.
    await bot_roles.espelli(membro, reason="y")
    assert client.http.kick.await_count == 1
    assert membro.kick.await_count == 2


@pytest.mark.asyncio
async def test_mod_rifiutato_riprova_il_principale_una_volta():
    client, _ = _mod()
    client.http.delete_message.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    guild = _principale()
    messaggio = MagicMock(spec=discord.Message)
    messaggio.id = 1
    messaggio.guild = guild
    messaggio.channel = fake_text_channel(channel_id=2)
    messaggio.delete = AsyncMock()
    await bot_roles.cancella_messaggio(messaggio)
    client.http.delete_message.assert_awaited_once_with(2, 1)
    messaggio.delete.assert_awaited_once()


def test_mod_e_il_principale_non_sono_attaccanti():
    client, _ = _mod()
    principale = MagicMock(spec=discord.Client)
    principale.user = fake_member(user_id=999, bot=True)
    assert bot_roles.e_un_nostro_bot(999, principale)
    assert bot_roles.e_un_nostro_bot(4242, principale)
    assert not bot_roles.e_un_nostro_bot(5, principale)
    assert not bot_roles.e_un_nostro_bot(None, principale)


def test_mod_non_ascolta_eventi_ne_chiede_intent_privilegiati():
    mod = ModBot()
    assert not mod.intents.members and not mod.intents.message_content
    assert mod.intents.guilds
    # Nessun gestore di eventi: ogni evento lo gestisce solo il principale.
    assert not [n for n in dir(type(mod)) if n.startswith("on_") and n not in dir(discord.Client)]
    assert mod.http.max_ratelimit_timeout == 30.0


# --- Log: il router scrive con un bot solo


def _canali_principale_e_mod(server_mod):
    principale = _principale()
    del principale.get_thread
    canale = fake_text_channel(channel_id=50)
    canale.guild = principale
    principale.get_channel.side_effect = {50: canale}.get
    suo = fake_text_channel(channel_id=50)
    suo.guild = server_mod
    suo.permissions_for.return_value = discord.Permissions.all()
    server_mod.get_channel.side_effect = {50: suo}.get
    return principale, canale, suo


@pytest.mark.asyncio
async def test_router_scrive_una_volta_sola_con_mod(monkeypatch):
    router_senza_scelte(monkeypatch)
    _, server_mod = _mod()
    principale, canale, suo = _canali_principale_e_mod(server_mod)
    dest = await router.destinazione(principale, router.TIPO_EVENTI, 50)
    assert dest is suo
    assert await router.invia_a(dest, principale, router.TIPO_EVENTI, embed=discord.Embed(title="x"))
    suo.send.assert_awaited_once()
    canale.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_senza_mod_scrive_il_principale(monkeypatch):
    router_senza_scelte(monkeypatch)
    principale = _principale()
    canale = fake_text_channel(channel_id=50)
    canale.guild = principale
    principale.get_channel.side_effect = {50: canale}.get
    dest = await router.destinazione(principale, router.TIPO_EVENTI, 50)
    assert dest is canale


@pytest.mark.asyncio
async def test_router_mod_senza_permesso_riprova_il_principale(monkeypatch):
    router_senza_scelte(monkeypatch)
    _, server_mod = _mod()
    principale, canale, suo = _canali_principale_e_mod(server_mod)
    suo.send.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    dest = await router.destinazione(principale, router.TIPO_EVENTI, 50)
    assert await router.invia_a(dest, principale, router.TIPO_EVENTI, content="x")
    suo.send.assert_awaited_once()
    canale.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_messaggio_con_bottoni_lo_scrive_il_principale(monkeypatch):
    router_senza_scelte(monkeypatch)
    _, server_mod = _mod()
    principale, canale, suo = _canali_principale_e_mod(server_mod)
    dest = await router.destinazione(principale, router.TIPO_EVENTI, 50)
    await router.invia_a(dest, principale, router.TIPO_EVENTI, content="x", view=MagicMock())
    canale.send.assert_awaited_once()
    suo.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_scrivi_usa_mod_e_ripiega_sul_principale():
    _, server_mod = _mod()
    _, canale, suo = _canali_principale_e_mod(server_mod)
    await bot_roles.scrivi(canale, content="a")
    suo.send.assert_awaited_once()
    canale.send.assert_not_awaited()
    suo.send.side_effect = discord.RateLimited(60.0)
    bot_roles.registra_mod(bot_roles.client_mod())  # azzera il fermo
    await bot_roles.scrivi(canale, content="b")
    canale.send.assert_awaited_once()
