"""
tests/test_channel_router.py
============================
Router dei canali (NF-01): canale di testo, forum con un post per tipo,
canale sparito o senza permesso con un solo avviso, canali offuscati.
"""

from unittest.mock import AsyncMock, MagicMock

import asyncio

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
    router._post_noti.clear()
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
    post.parent_id = 8
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
    nuovo.parent_id = 8
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


# ---- correzioni dopo il controllo del cacciatore-bug
@pytest.mark.asyncio
async def test_canale_generale_cancellato_poi_nuovo_generale_la_destinazione_torna_valida(repo):
    owner = fake_member(user_id=555)
    assert await router.destinazione(_server(owner=owner), router.TIPO_MESSAGGI, 77) is None
    assert owner.send.await_count == 1
    nuovo = fake_text_channel(88)
    for tipo in router.TIPI_LOG:
        assert await router.destinazione(_server(nuovo, owner=owner), tipo, 88) is nuovo
    assert owner.send.await_count == 1


@pytest.mark.asyncio
async def test_nuovo_avviso_se_il_nuovo_generale_sparisce_a_sua_volta(repo):
    owner = fake_member(user_id=555)
    await router.destinazione(_server(owner=owner), router.TIPO_VOCE, 77)
    await router.destinazione(_server(owner=owner), router.TIPO_VOCE, 88)
    assert owner.send.await_count == 2


@pytest.mark.asyncio
async def test_la_scelta_esplicita_del_tipo_resta_dopo_il_cambio_del_generale(repo):
    messaggi, nuovo = fake_text_channel(1), fake_text_channel(88)
    await repo.imposta(900, router.TIPO_MESSAGGI, 1)
    assert await router.destinazione(_server(messaggi, nuovo), router.TIPO_MESSAGGI, 88) is messaggi


@pytest.mark.asyncio
async def test_il_post_nato_dal_generale_non_blocca_il_cambio_da_forum_a_testo(repo):
    forum = fake_forum_channel(50)
    post = MagicMock(spec=discord.Thread, id=5000, parent_id=50)
    post.send = AsyncMock()
    forum.create_thread = AsyncMock(return_value=MagicMock(thread=post, message=MagicMock()))
    server = _server(forum)
    forum.guild = server
    dest = await router.destinazione(server, router.TIPO_MESSAGGI, 50)
    await router.invia_a(dest, server, router.TIPO_MESSAGGI, embed=discord.Embed(title="x"))
    nuovo = fake_text_channel(88)
    assert await router.destinazione(_server(nuovo, forum), router.TIPO_MESSAGGI, 88) is nuovo


@pytest.mark.asyncio
async def test_tre_invii_insieme_nel_forum_creano_un_solo_post(repo):
    forum = fake_forum_channel(50)
    server = _server(forum)
    forum.guild = server
    post = MagicMock(spec=discord.Thread, id=7001, parent_id=50)
    post.send = AsyncMock()

    async def crea(**kw):
        await asyncio.sleep(0.05)
        return MagicMock(thread=post, message=MagicMock())

    forum.create_thread = AsyncMock(side_effect=crea)
    dest = await router.destinazione(server, router.TIPO_MESSAGGI, 50)
    await asyncio.gather(*(dest.send(embed=discord.Embed(title=str(n))) for n in range(3)))
    assert forum.create_thread.await_count == 1
    assert post.send.await_count == 2


@pytest.mark.asyncio
async def test_post_archiviato_non_in_cache_si_ritrova_e_non_ne_nasce_un_altro(repo):
    forum = fake_forum_channel(50)
    server = _server(forum)
    forum.guild = server
    archiviato = MagicMock(spec=discord.Thread, id=7002)
    archiviato.send = AsyncMock()
    server.fetch_channel = AsyncMock(return_value=archiviato)
    forum.create_thread = AsyncMock()
    await repo.imposta(900, router.TIPO_VOCE, 50)
    await repo.salva_post(900, router.TIPO_VOCE, 50, 7002)
    dest = await router.destinazione(server, router.TIPO_VOCE, None)
    await dest.send(embed=discord.Embed(title="x"))
    archiviato.send.assert_awaited_once()
    forum.create_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_il_file_si_riavvolge_se_il_post_non_c_e_piu(repo):
    forum = fake_forum_channel(50)
    server = _server(forum)
    forum.guild = server
    vecchio = MagicMock(spec=discord.Thread, id=7003)
    vecchio.send = AsyncMock(side_effect=discord.NotFound(_risposta(404), "x"))
    nuovo = MagicMock(spec=discord.Thread, id=7004)
    server.get_thread.return_value = vecchio
    forum.create_thread = AsyncMock(return_value=MagicMock(thread=nuovo, message=MagicMock()))
    await repo.imposta(900, router.TIPO_VOCE, 50)
    await repo.salva_post(900, router.TIPO_VOCE, 50, 7003)
    file = MagicMock(spec=discord.File)
    dest = await router.destinazione(server, router.TIPO_VOCE, None)
    await dest.send(file=file)
    file.reset.assert_called_once()


@pytest.mark.asyncio
async def test_proprietario_non_in_memoria_l_avviso_non_si_perde(repo):
    owner = fake_member(user_id=555)
    await repo.imposta(900, router.TIPO_EVENTI, 77)
    await router.destinazione(_server(owner=None), router.TIPO_EVENTI, None)
    assert not (await repo.ottieni(900, router.TIPO_EVENTI)).avvisato
    for _ in range(3):
        await router.destinazione(_server(owner=owner), router.TIPO_EVENTI, None)
    assert owner.send.await_count == 1


@pytest.mark.asyncio
async def test_dm_chiusi_l_avviso_si_considera_dato(repo):
    owner = fake_member(user_id=555)
    owner.send = AsyncMock(side_effect=discord.Forbidden(_risposta(403), "dm"))
    await repo.imposta(900, router.TIPO_EVENTI, 77)
    for _ in range(3):
        await router.destinazione(_server(owner=owner), router.TIPO_EVENTI, None)
    assert owner.send.await_count == 1


@pytest.mark.asyncio
async def test_cambiando_forum_il_log_va_nel_forum_nuovo_non_nel_post_vecchio(repo):
    vecchio_forum, nuovo_forum = fake_forum_channel(50), fake_forum_channel(60)
    server = _server(vecchio_forum, nuovo_forum)
    vecchio_forum.guild = nuovo_forum.guild = server
    post_vecchio = MagicMock(spec=discord.Thread, id=1, parent_id=50)
    post_vecchio.send = AsyncMock()
    post_nuovo = MagicMock(spec=discord.Thread, id=2, parent_id=60)
    post_nuovo.send = AsyncMock()
    vecchio_forum.create_thread = AsyncMock(return_value=MagicMock(thread=post_vecchio, message=MagicMock()))
    nuovo_forum.create_thread = AsyncMock(return_value=MagicMock(thread=post_nuovo, message=MagicMock()))

    await repo.imposta(900, router.TIPO_VOCE, 50)
    dest = await router.destinazione(server, router.TIPO_VOCE, None)
    await dest.send(embed=discord.Embed(title="a"))
    await repo.imposta(900, router.TIPO_VOCE, 60)  # /log canale tipo:voce nel forum nuovo
    dest = await router.destinazione(server, router.TIPO_VOCE, None)
    await dest.send(embed=discord.Embed(title="b"))

    nuovo_forum.create_thread.assert_awaited_once()
    post_vecchio.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_il_post_di_un_altro_forum_nella_riga_non_si_usa(repo):
    forum = fake_forum_channel(60)
    server = _server(forum)
    forum.guild = server
    altro = MagicMock(spec=discord.Thread, id=3)
    altro.send = AsyncMock()
    server.get_thread.return_value = altro
    nuovo = MagicMock(spec=discord.Thread, id=4, parent_id=60)
    forum.create_thread = AsyncMock(return_value=MagicMock(thread=nuovo, message=MagicMock()))
    await repo.imposta(900, router.TIPO_VOCE, 50)
    await repo.salva_post(900, router.TIPO_VOCE, 50, 3)  # post del forum 50
    await repo.imposta(900, router.TIPO_VOCE, 60)  # poi si passa al forum 60
    dest = await router.destinazione(server, router.TIPO_VOCE, None)
    await dest.send(embed=discord.Embed(title="x"))
    altro.send.assert_not_awaited()
    forum.create_thread.assert_awaited_once()


@pytest.mark.asyncio
async def test_riga_di_un_altro_canale_non_fissa_la_destinazione_del_generale(repo):
    vecchio, generale = fake_text_channel(77), fake_text_channel(88)
    await repo.segna_avvisato(900, router.TIPO_SERVER, 77)  # riga non esplicita sul canale 77
    assert await router.destinazione(_server(vecchio, generale), router.TIPO_SERVER, 88) is generale


@pytest.mark.asyncio
async def test_salva_post_non_sposta_una_scelta_esplicita(repo):
    await repo.imposta(900, router.TIPO_VOCE, 50)
    await repo.salva_post(900, router.TIPO_VOCE, 99, 7)
    riga = await repo.ottieni(900, router.TIPO_VOCE)
    assert riga.channel_id == 50 and riga.esplicito and riga.post_id == 7


@pytest.mark.asyncio
async def test_due_avvisi_insieme_mandano_un_solo_dm(repo):
    owner = fake_member(user_id=555)
    gate = asyncio.Event()

    async def lento(*a, **k):
        await gate.wait()

    owner.send = AsyncMock(side_effect=lento)
    server = _server(owner=owner)
    primo = asyncio.create_task(router.avvisa_proprietario(server, router.TIPO_EVENTI, 77, "x"))
    await asyncio.sleep(0.05)
    await router.avvisa_proprietario(server, router.TIPO_EVENTI, 77, "x")  # mentre il primo è in corso
    gate.set()
    await primo
    assert owner.send.await_count == 1


@pytest.mark.asyncio
async def test_dm_fallito_per_errore_di_rete_non_segna_l_avviso(repo):
    owner = fake_member(user_id=555)
    owner.send = AsyncMock(side_effect=discord.HTTPException(_risposta(500), "boom"))
    await router.avvisa_proprietario(_server(owner=owner), router.TIPO_EVENTI, 77, "x")
    riga = await repo.ottieni(900, router.TIPO_EVENTI)
    assert riga is None or not riga.avvisato
