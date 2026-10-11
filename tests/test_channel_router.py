"""
tests/test_channel_router.py
============================
Router dei canali (NF-01): canale di testo, forum con un post per tipo,
canale sparito o senza permesso con un solo avviso, canali offuscati.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.channel_router as router
from core.repositories.output_channel_repo import OutputChannelRepository
from tests.support.discord_fakes import (
    fake_forum_channel,
    fake_guild,
    fake_member,
    fake_text_channel,
)


@pytest.fixture
def repo(clean_db, monkeypatch):
    repo = OutputChannelRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(router, "output_channel_repo", repo)
    router._avvisati.clear()
    return repo


def _server(*canali, owner=None):
    server = fake_guild(guild_id=900)
    mappa = {c.id: c for c in canali}
    server.get_channel.side_effect = mappa.get
    server.get_thread = MagicMock(return_value=None)
    server.get_member = MagicMock(return_value=owner)
    return server


def _risposta(stato):
    r = MagicMock()
    r.status = stato
    r.reason = "x"
    return r


@pytest.mark.asyncio
async def test_il_canale_del_tipo_vince_sul_predefinito(repo):
    messaggi, generale = fake_text_channel(1), fake_text_channel(2)
    await repo.imposta(900, router.TIPO_MESSAGGI, 1)
    dest = await router.destinazione(_server(messaggi, generale), router.TIPO_MESSAGGI, 2)
    assert dest is messaggi


@pytest.mark.asyncio
async def test_senza_riga_si_usa_il_predefinito(repo):
    generale = fake_text_channel(2)
    dest = await router.destinazione(_server(generale), router.TIPO_VOCE, 2)
    assert dest is generale


@pytest.mark.asyncio
async def test_senza_niente_configurato_nessuna_destinazione(repo):
    assert await router.destinazione(_server(), router.TIPO_SERVER, None) is None


@pytest.mark.asyncio
async def test_canale_offuscato_viene_ignorato(repo):
    nascosto = fake_text_channel(3, name="___hidden___")
    assert await router.destinazione(_server(nascosto), router.TIPO_EVENTI, 3) is None
    assert router.canale_nascosto(nascosto)
    assert not router.canale_nascosto(fake_text_channel(4, name="log"))


@pytest.mark.asyncio
async def test_canale_sparito_avvisa_il_proprietario_una_volta_sola(repo):
    owner = fake_member(user_id=555)
    server = _server(owner=owner)
    await repo.imposta(900, router.TIPO_EVENTI, 77)
    for _ in range(3):
        assert await router.destinazione(server, router.TIPO_EVENTI, None) is None
    assert owner.send.await_count == 1


@pytest.mark.asyncio
async def test_senza_permesso_un_solo_avviso_poi_si_riarma_al_primo_invio_riuscito(repo):
    owner = fake_member(user_id=555)
    canale = fake_text_channel(5)
    server = _server(canale, owner=owner)
    canale.guild = server
    canale.send = AsyncMock(side_effect=discord.Forbidden(_risposta(403), "no"))
    for _ in range(3):
        assert not await router.invia_a(canale, server, router.TIPO_EVENTI, embed=discord.Embed())
    assert owner.send.await_count == 1

    canale.send = AsyncMock()
    assert await router.invia_a(canale, server, router.TIPO_EVENTI, embed=discord.Embed())
    canale.send = AsyncMock(side_effect=discord.Forbidden(_risposta(403), "no"))
    await router.invia_a(canale, server, router.TIPO_EVENTI, embed=discord.Embed())
    assert owner.send.await_count == 2


@pytest.mark.asyncio
async def test_errore_diverso_da_permesso_non_avvisa(repo):
    owner = fake_member(user_id=555)
    canale = fake_text_channel(5)
    server = _server(canale, owner=owner)
    canale.send = AsyncMock(side_effect=discord.HTTPException(_risposta(500), "boom"))
    assert not await router.invia_a(canale, server, router.TIPO_EVENTI, embed=discord.Embed())
    owner.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_avviso_al_proprietario_con_dm_chiusi_non_solleva(repo):
    owner = fake_member(user_id=555)
    owner.send = AsyncMock(side_effect=discord.Forbidden(_risposta(403), "dm"))
    server = _server(owner=owner)
    await repo.imposta(900, router.TIPO_EVENTI, 77)
    assert await router.destinazione(server, router.TIPO_EVENTI, None) is None


@pytest.mark.asyncio
async def test_forum_il_primo_invio_crea_il_post_poi_si_riusa(repo):
    forum = fake_forum_channel(8)
    post = MagicMock(spec=discord.Thread)
    post.id = 801
    post.send = AsyncMock()
    forum.create_thread = AsyncMock(
        return_value=MagicMock(thread=post, message=MagicMock())
    )
    server = _server(forum)
    forum.guild = server
    await repo.imposta(900, router.TIPO_MESSAGGI, 8)

    dest = await router.destinazione(server, router.TIPO_MESSAGGI, None)
    assert await router.invia_a(dest, server, router.TIPO_MESSAGGI, embed=discord.Embed(title="a"))
    forum.create_thread.assert_awaited_once()
    assert forum.create_thread.await_args.kwargs["name"] == router.NOME_POST[router.TIPO_MESSAGGI]
    assert (await repo.ottieni(900, router.TIPO_MESSAGGI)).post_id == 801

    server.get_thread.return_value = post
    dest = await router.destinazione(server, router.TIPO_MESSAGGI, None)
    assert await router.invia_a(dest, server, router.TIPO_MESSAGGI, embed=discord.Embed(title="b"))
    forum.create_thread.assert_awaited_once()
    post.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_forum_post_cancellato_ne_nasce_uno_nuovo(repo):
    forum = fake_forum_channel(8)
    nuovo = MagicMock(spec=discord.Thread)
    nuovo.id = 802
    vecchio = MagicMock(spec=discord.Thread)
    vecchio.id = 801
    vecchio.send = AsyncMock(side_effect=discord.NotFound(_risposta(404), "x"))
    forum.create_thread = AsyncMock(return_value=MagicMock(thread=nuovo, message=MagicMock()))
    server = _server(forum)
    server.get_thread.return_value = vecchio
    forum.guild = server
    await repo.imposta(900, router.TIPO_VOCE, 8)
    await repo.salva_post(900, router.TIPO_VOCE, 8, 801)

    dest = await router.destinazione(server, router.TIPO_VOCE, None)
    assert await router.invia_a(dest, server, router.TIPO_VOCE, embed=discord.Embed(title="x"))
    assert (await repo.ottieni(900, router.TIPO_VOCE)).post_id == 802


@pytest.mark.asyncio
async def test_repo_segna_avvisato_vale_una_volta_e_imposta_lo_azzera(repo):
    assert await repo.segna_avvisato(1, "eventi", 5) is True
    assert await repo.segna_avvisato(1, "eventi", 5) is False
    await repo.imposta(1, "eventi", 6)
    assert await repo.segna_avvisato(1, "eventi", 6) is True
    assert [r.tipo for r in await repo.elenco(1)] == ["eventi"]
    assert await repo.rimuovi(1, "eventi") is True
    assert await repo.rimuovi(1, "eventi") is False
