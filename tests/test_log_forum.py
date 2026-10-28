"""
tests/test_log_forum.py
=======================
Vista dei log su un forum (SPEC §8.17): un post per canale o per caso. Logica pura,
tabelle vere, servizio con un forum finto e comando /log vista-forum.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.logging.log_config as modulo
from core import log_forum_service as servizio
from core.log_forum_logic import (
    CODA_MAX,
    DIM_CANALI,
    DIM_CASI,
    MAX_POST_PER_DIMENSIONE,
    descrizione_caso,
    descrizione_evento,
    titolo_post,
)
from core.repositories.log_forum_repo import LogForumRepository
from tests.support.discord_fakes import fake_forum_channel, fake_guild, fake_interaction

SERVER = 600


# ------------------------------------------------------------------ logica pura
def test_titoli_dei_post():
    assert titolo_post(DIM_CASI, 12) == "Caso #12"
    assert titolo_post(DIM_CANALI, 5, "generale") == "#generale"
    assert titolo_post(DIM_CANALI, 5) == "#5"
    assert len(titolo_post(DIM_CANALI, 5, "x" * 300)) == 100


def test_descrizione_evento_con_tutti_i_campi_e_dettagli_tagliati():
    testo = descrizione_evento(
        "role_edit", actor_id=1, target_user_id=2, role_id=3, case_number=4, details={"nome": "`" + "a" * 900}
    )
    assert "<@1>" in testo and "<@2>" in testo and "<@&3>" in testo and "caso #4" in testo
    assert "…" in testo and len(testo) < 800
    assert "``" not in testo


def test_descrizione_caso_apertura_e_revoca():
    aperto = descrizione_caso(7, "ban", user_id=2, moderator_id=3, motivo="spam")
    assert "Caso #7" in aperto and "ban" in aperto and "<@3>" in aperto and "spam" in aperto
    assert "revocato da <@9>" in descrizione_caso(7, "ban", user_id=2, moderator_id=3, revocato_da=9)


# ------------------------------------------------------------------ tabelle
@pytest.fixture
def repo(clean_db):
    return LogForumRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_forum_scelti_e_post(repo):
    await repo.imposta_forum(SERVER, DIM_CANALI, 11)
    await repo.imposta_forum(SERVER, DIM_CASI, 12)
    assert await repo.forum_del_server(SERVER) == {DIM_CANALI: 11, DIM_CASI: 12}
    assert await repo.forum_del_server(SERVER + 1) == {}

    await repo.salva_post(SERVER, DIM_CANALI, 5, 901)
    assert await repo.post_di(SERVER, DIM_CANALI, 5) == 901
    assert await repo.conta_post(SERVER, DIM_CANALI) == 1
    await repo.dimentica_post(SERVER, DIM_CANALI, 5)
    assert await repo.post_di(SERVER, DIM_CANALI, 5) is None


@pytest.mark.asyncio
async def test_cambiare_o_togliere_il_forum_dimentica_i_post_di_quella_vista(repo):
    await repo.imposta_forum(SERVER, DIM_CANALI, 11)
    await repo.imposta_forum(SERVER, DIM_CASI, 12)
    await repo.salva_post(SERVER, DIM_CANALI, 5, 901)
    await repo.salva_post(SERVER, DIM_CASI, 3, 902)

    await repo.imposta_forum(SERVER, DIM_CANALI, 13)  # altro forum: i vecchi post non valgono
    assert await repo.post_di(SERVER, DIM_CANALI, 5) is None
    assert await repo.post_di(SERVER, DIM_CASI, 3) == 902

    assert await repo.togli_forum(SERVER, DIM_CASI) is True
    assert await repo.togli_forum(SERVER, DIM_CASI) is False
    assert await repo.post_di(SERVER, DIM_CASI, 3) is None
    assert await repo.forum_del_server(SERVER) == {DIM_CANALI: 13}


# ------------------------------------------------------------------ servizio
def _post(post_id, forum_id):
    post = MagicMock(spec=discord.Thread)
    post.id = post_id
    post.parent_id = forum_id
    post.send = AsyncMock()
    return post


@pytest.fixture
def mondo(repo, monkeypatch):
    forum = fake_forum_channel(77)
    canale = MagicMock()
    canale.name = "regole"
    server = fake_guild(SERVER)
    server.get_channel.side_effect = lambda i: {77: forum, 5: canale}.get(i)
    server.get_thread.return_value = None
    server.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404, reason="x"), "no"))
    forum.guild = server
    bot = MagicMock()
    bot.get_guild.return_value = server
    nuovo = _post(900, 77)
    forum.create_thread = AsyncMock(return_value=MagicMock(thread=nuovo, message=MagicMock()))
    monkeypatch.setattr(servizio, "log_forum_repo", repo)
    monkeypatch.setattr(servizio, "_bot", bot)
    monkeypatch.setattr(servizio, "_coda", asyncio.Queue(maxsize=CODA_MAX))
    servizio._viste.clear()
    yield forum, server, nuovo
    servizio._viste.clear()


@pytest.mark.asyncio
async def test_senza_forum_scelto_non_si_accoda_niente(mondo):
    await servizio.notifica_evento(SERVER, "channel_update", channel_id=5)
    await servizio.notifica_caso(SERVER, 3, "ban", user_id=2, moderator_id=3)
    assert servizio._coda.empty()


@pytest.mark.asyncio
async def test_senza_avvio_la_vista_non_fa_nulla(repo, monkeypatch):
    monkeypatch.setattr(servizio, "_bot", None)
    await servizio.notifica_evento(SERVER, "x", channel_id=5)  # non solleva


@pytest.mark.asyncio
async def test_un_evento_con_canale_va_nella_vista_dei_canali_e_con_caso_in_quella_dei_casi(mondo, repo):
    await repo.imposta_forum(SERVER, DIM_CANALI, 77)
    await servizio.notifica_evento(SERVER, "message_delete", channel_id=5, actor_id=1, case_number=4)
    assert servizio._coda.qsize() == 1  # i casi non hanno la vista accesa
    await repo.imposta_forum(SERVER, DIM_CASI, 77)
    servizio.invalida(SERVER)
    await servizio.notifica_evento(SERVER, "message_delete", channel_id=5, case_number=4)
    assert servizio._coda.qsize() == 3
    await servizio.notifica_evento(SERVER, "member_join", target_user_id=9)  # niente canale, niente caso
    assert servizio._coda.qsize() == 3


@pytest.mark.asyncio
async def test_la_coda_piena_perde_gli_eventi_nuovi_senza_errori(mondo, repo, monkeypatch):
    await repo.imposta_forum(SERVER, DIM_CANALI, 77)
    monkeypatch.setattr(servizio, "_coda", asyncio.Queue(maxsize=2))
    for _ in range(5):
        await servizio.notifica_evento(SERVER, "x", channel_id=5)
    assert servizio._coda.qsize() == 2


@pytest.mark.asyncio
async def test_il_primo_evento_crea_il_post_poi_si_riusa(mondo, repo):
    forum, server, nuovo = mondo
    await repo.imposta_forum(SERVER, DIM_CANALI, 77)
    assert await servizio.scrivi(SERVER, DIM_CANALI, 5, "uno")
    forum.create_thread.assert_awaited_once()
    assert forum.create_thread.await_args.kwargs["name"] == "#regole"
    assert await repo.post_di(SERVER, DIM_CANALI, 5) == 900

    server.get_thread.return_value = nuovo
    assert await servizio.scrivi(SERVER, DIM_CANALI, 5, "due")
    forum.create_thread.assert_awaited_once()
    nuovo.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_cancellato_ne_nasce_uno_nuovo(mondo, repo):
    forum, server, nuovo = mondo
    await repo.imposta_forum(SERVER, DIM_CASI, 77)
    await repo.salva_post(SERVER, DIM_CASI, 3, 555)  # il thread 555 non esiste più (fetch_channel: NotFound)
    assert await servizio.scrivi(SERVER, DIM_CASI, 3, "caso")
    assert forum.create_thread.await_args.kwargs["name"] == "Caso #3"
    assert await repo.post_di(SERVER, DIM_CASI, 3) == 900


@pytest.mark.asyncio
async def test_oltre_il_tetto_i_canali_nuovi_non_hanno_il_post(mondo, repo, monkeypatch):
    forum, _, _ = mondo
    await repo.imposta_forum(SERVER, DIM_CANALI, 77)
    monkeypatch.setattr(repo, "conta_post", AsyncMock(return_value=MAX_POST_PER_DIMENSIONE))
    assert await servizio.scrivi(SERVER, DIM_CANALI, 5, "x") is False
    forum.create_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_forum_sparito_dal_server_non_scrive(mondo, repo):
    forum, server, _ = mondo
    await repo.imposta_forum(SERVER, DIM_CANALI, 78)  # un forum che il server non ha più
    assert await servizio.scrivi(SERVER, DIM_CANALI, 5, "x") is False
    forum.create_thread.assert_not_awaited()


# ------------------------------------------------------------------ i due punti di scrittura
@pytest.mark.asyncio
async def test_il_registro_degli_eventi_e_dei_casi_avvisano_la_vista(clean_db, monkeypatch):
    from core.repositories.event_log_repo import EventLogRepository
    from core.repositories.moderation_repo import ModerationRepository

    evento = AsyncMock()
    caso = AsyncMock()
    monkeypatch.setattr(servizio, "notifica_evento", evento)
    monkeypatch.setattr(servizio, "notifica_caso", caso)
    eventi = EventLogRepository(pool_provider=lambda: clean_db)
    await eventi.log_event(SERVER, "channel_update", channel_id=5)
    assert evento.await_args.args[:2] == (SERVER, "channel_update") and evento.await_args.kwargs["channel_id"] == 5

    moderazione = ModerationRepository(pool_provider=lambda: clean_db)
    numero = await moderazione.create_case(SERVER, 2, 3, "ban", "spam")
    assert caso.await_args.args[:3] == (SERVER, numero, "ban") and caso.await_args.kwargs["motivo"] == "spam"
    assert await moderazione.revoke_case(SERVER, numero, 9) is True
    assert caso.await_args.kwargs["revocato_da"] == 9
    caso.reset_mock()
    assert await moderazione.revoke_case(SERVER, numero, 9) is False  # già revocato: nessun avviso
    caso.assert_not_awaited()


# ------------------------------------------------------------------ comando
def _scena(repo, monkeypatch, permessi=None):
    monkeypatch.setattr(servizio, "log_forum_repo", repo)
    server = fake_guild(SERVER)
    server.me.guild_permissions = discord.Permissions.all()
    forum = fake_forum_channel(77)
    forum.permissions_for.return_value = permessi if permessi is not None else discord.Permissions.all()
    return server, forum, fake_interaction(guild=server)


@pytest.mark.asyncio
async def test_il_comando_accende_e_spegne_la_vista(repo, monkeypatch):
    server, forum, i = _scena(repo, monkeypatch)
    cog = modulo.LogConfigCog(MagicMock())
    await cog.vista_forum.callback(cog, i, DIM_CASI, forum)
    assert await repo.forum_del_server(SERVER) == {DIM_CASI: 77}
    assert "un post per ogni caso" in i.response.send_message.await_args.args[0]

    i2 = fake_interaction(guild=server)
    await cog.vista_forum.callback(cog, i2, DIM_CASI, None)
    assert await repo.forum_del_server(SERVER) == {}
    assert "spenta" in i2.response.send_message.await_args.args[0]

    i3 = fake_interaction(guild=server)
    await cog.vista_forum.callback(cog, i3, DIM_CASI, None)
    assert "non era accesa" in i3.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_il_comando_rifiuta_un_forum_senza_i_permessi(repo, monkeypatch):
    server, forum, i = _scena(repo, monkeypatch, permessi=discord.Permissions(view_channel=True))
    cog = modulo.LogConfigCog(MagicMock())
    await cog.vista_forum.callback(cog, i, DIM_CANALI, forum)
    assert await repo.forum_del_server(SERVER) == {}
    assert "create_public_threads" in i.response.send_message.await_args.args[0]
