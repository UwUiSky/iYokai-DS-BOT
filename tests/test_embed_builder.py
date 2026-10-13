"""
tests/test_embed_builder.py
===========================
NF-17 (#88): costruttore di embed. Tutti i limiti (256, 4096, 1024, 25, 6000) controllati al
salvataggio; anteprima; pubblica e modifica anche dopo; indirizzi delle immagini controllati.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.embed_builder as modulo
from cogs.utility.embed_builder import EmbedBuilderCog
from core.embed_builder_logic import (
    MAX_EMBED,
    DatiEmbed,
    a_json,
    costruisci,
    da_json,
    lunghezza_totale,
    valida,
)
from core.repositories.saved_embed_repo import SavedEmbedRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_text_channel
from tests.support.percorsi import comando_nel_gruppo


def _e(**kw):
    base = dict(title="Titolo", description="Testo")
    base.update(kw)
    return DatiEmbed(**base)


# ---------------------------------------------------------------- logica pura
def test_embed_valido_senza_errori():
    assert valida(_e()) == []


def test_embed_vuoto_rifiutato():
    assert valida(DatiEmbed()) != []


@pytest.mark.parametrize(
    "dati",
    [
        _e(title="t" * 257),
        _e(description="d" * 4097),
        _e(footer="f" * 2049),
        _e(fields=(("n", "v", False),) * 26),
        _e(fields=(("n" * 257, "v", False),)),
        _e(fields=(("n", "v" * 1025, False),)),
        _e(fields=(("", "v", False),)),
        _e(description="d" * 4000, fields=(("n", "v" * 1000, False), ("n", "v" * 1000, False))),  # oltre 6000 in tutto
        _e(color="rosso"),
        _e(image_url="ftp://x/y.png"),
        _e(image_url="https://x/" + "a" * 2100),
        _e(thumbnail_url="javascript:alert(1)"),
    ],
)
def test_limiti_rifiutati_al_salvataggio(dati):
    assert valida(dati) != []


def test_al_limite_esatto_passa():
    ok = _e(title="t" * 256, description="d" * 4000, footer="f" * 100,
            fields=(("n", "v" * 100, False),) * 12)
    assert valida(ok) == []
    assert valida(_e(title="t" * 256, description="d" * 4096, fields=(("n", "v", False),) * 25)) == []


def test_lunghezza_totale_combacia_con_discord():
    dati = _e(footer="piede", fields=(("campo", "valore", True),))
    assert lunghezza_totale(dati) == len(costruisci(dati))


def test_costruisci_usa_colore_e_campi():
    embed = costruisci(_e(color="#ff8800", fields=(("a", "b", True),), image_url="https://x/y.png"))
    assert embed.colour.value == 0xFF8800
    assert embed.fields[0].inline is True and embed.image.url == "https://x/y.png"


def test_json_andata_e_ritorno():
    dati = _e(color="#FF8800", fields=(("a", "b", True),), footer="p")
    assert da_json(json.loads(a_json(dati))) == dati


# --------------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return SavedEmbedRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_salva_leggi_elenca_elimina(repo):
    assert await repo.create(1, "annuncio", a_json(_e()), created_by=7) == "ok"
    assert await repo.create(1, "ANNUNCIO", a_json(_e()), created_by=7) == "esiste"
    salvato = await repo.get(1, "annuncio")
    assert da_json(salvato.data) == _e() and salvato.message_id is None
    assert [s.name for s in await repo.list(1)] == ["annuncio"]
    assert await repo.delete(1, "annuncio") is True
    assert await repo.get(1, "annuncio") is None


@pytest.mark.asyncio
async def test_tetto_per_server(repo):
    for i in range(MAX_EMBED):
        assert await repo.create(1, f"e{i}", a_json(_e()), created_by=7) == "ok"
    assert await repo.create(1, "troppo", a_json(_e()), created_by=7) == "pieno"
    assert await repo.create(2, "troppo", a_json(_e()), created_by=7) == "ok"


@pytest.mark.asyncio
async def test_aggiorna_dati_e_pubblicazione(repo):
    await repo.create(1, "a", a_json(_e()), created_by=7)
    assert await repo.update_data(1, "a", a_json(_e(title="Nuovo"))) is True
    assert da_json((await repo.get(1, "a")).data).title == "Nuovo"
    await repo.set_published(1, "a", 700, 800)
    s = await repo.get(1, "a")
    assert (s.channel_id, s.message_id) == (700, 800)
    await repo.set_published(1, "a", None, None)
    assert (await repo.get(1, "a")).message_id is None


# -------------------------------------------------------------------------- cog
@pytest.fixture
def scena(monkeypatch):
    cog = EmbedBuilderCog(MagicMock())
    repo = MagicMock()
    repo.create = AsyncMock(return_value="ok")
    repo.get = AsyncMock(return_value=SimpleNamespace(name="a", data=json.loads(a_json(_e())), channel_id=None, message_id=None))
    repo.update_data = AsyncMock(return_value=True)
    repo.set_published = AsyncMock()
    repo.list = AsyncMock(return_value=[])
    repo.delete = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "saved_embed_repo", repo)
    monkeypatch.setattr(modulo, "url_e_sicuro", AsyncMock(return_value=True))
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", db_finto)
    cog.repo = repo
    return cog


@pytest.mark.asyncio
async def test_crea_salva_e_mostra_l_anteprima(scena):
    i = fake_interaction()
    await scena.crea.callback(scena, i, "annuncio", "Titolo", "Testo", "#ff0000", None, None, None)
    scena.repo.create.assert_awaited_once()
    kw = i.followup.send.await_args.kwargs
    assert isinstance(kw["embed"], discord.Embed) and kw["ephemeral"] is True


@pytest.mark.asyncio
async def test_crea_rifiuta_oltre_i_limiti_senza_salvare(scena):
    i = fake_interaction()
    await scena.crea.callback(scena, i, "annuncio", "t" * 300, "Testo", None, None, None, None)
    scena.repo.create.assert_not_awaited()
    testo = i.followup.send.await_args.args[0]
    assert "256" in testo


@pytest.mark.asyncio
async def test_crea_rifiuta_indirizzo_non_sicuro(scena, monkeypatch):
    monkeypatch.setattr(modulo, "url_e_sicuro", AsyncMock(return_value=False))
    i = fake_interaction()
    await scena.crea.callback(scena, i, "annuncio", "T", "x", None, "https://127.0.0.1/a.png", None, None)
    scena.repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_crea_nome_non_valido(scena):
    i = fake_interaction()
    await scena.crea.callback(scena, i, "nome con spazi", "T", "x", None, None, None, None)
    scena.repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_pubblica_manda_l_embed_e_ricorda_il_messaggio(scena):
    canale = fake_text_channel(900)
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, embed_links=True))
    canale.send = AsyncMock(return_value=SimpleNamespace(id=1234))
    i = fake_interaction()
    await scena.pubblica.callback(scena, i, "a", canale)
    assert isinstance(canale.send.await_args.kwargs["embed"], discord.Embed)
    assert canale.send.await_args.kwargs["allowed_mentions"].everyone is False
    scena.repo.set_published.assert_awaited_once_with(i.guild.id, "a", 900, 1234)


@pytest.mark.asyncio
async def test_pubblica_senza_permessi_non_invia(scena):
    canale = fake_text_channel(900)
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, embed_links=False))
    canale.send = AsyncMock()
    i = fake_interaction()
    await scena.pubblica.callback(scena, i, "a", canale)
    canale.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_modifica_aggiorna_il_messaggio_gia_pubblicato_prima_di_salvare(scena):
    scena.repo.get.return_value = SimpleNamespace(
        name="a", data=json.loads(a_json(_e())), channel_id=900, message_id=1234
    )
    messaggio = SimpleNamespace(edit=AsyncMock())
    canale = fake_text_channel(900)
    canale.fetch_message = AsyncMock(return_value=messaggio)
    server = fake_guild()
    server.get_channel = lambda cid: canale
    i = fake_interaction(guild=server)
    await scena.modifica.callback(scena, i, "a", titolo="Nuovo")
    messaggio.edit.assert_awaited_once()
    assert messaggio.edit.await_args.kwargs["embed"].title == "Nuovo"
    scena.repo.update_data.assert_awaited_once()


@pytest.mark.asyncio
async def test_modifica_con_discord_che_rifiuta_non_salva(scena):
    scena.repo.get.return_value = SimpleNamespace(
        name="a", data=json.loads(a_json(_e())), channel_id=900, message_id=1234
    )
    messaggio = SimpleNamespace(edit=AsyncMock(side_effect=discord.HTTPException(MagicMock(status=400, reason="x"), "no")))
    canale = fake_text_channel(900)
    canale.fetch_message = AsyncMock(return_value=messaggio)
    server = fake_guild()
    server.get_channel = lambda cid: canale
    i = fake_interaction(guild=server)
    await scena.modifica.callback(scena, i, "a", titolo="Nuovo")
    scena.repo.update_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_modifica_campi_aggiunge_e_toglie(scena):
    i = fake_interaction()
    await scena.modifica.callback(scena, i, "a", campo_nome="N", campo_valore="V", campo_inline=True)
    dati = da_json(json.loads(scena.repo.update_data.await_args.args[2]))
    assert dati.fields == (("N", "V", True),)
    scena.repo.get.return_value = SimpleNamespace(name="a", data=json.loads(a_json(dati)), channel_id=None, message_id=None)
    await scena.modifica.callback(scena, i, "a", togli_campo=1)
    assert da_json(json.loads(scena.repo.update_data.await_args.args[2])).fields == ()


@pytest.mark.asyncio
async def test_albero_dei_comandi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("embed-crea", "embed-modifica", "embed-pubblica", "embed-elenco", "embed-elimina"):
        assert comando_nel_gruppo("admin", f"messaggi {nome}") is not None
    crea = {o["name"]: o for o in comando_nel_gruppo("admin", "messaggi embed-crea").to_dict(bot.tree)["options"]}
    assert crea["titolo"]["max_length"] == 256 and crea["descrizione"]["max_length"] == 4096
    assert crea["piede"]["max_length"] == 2048
