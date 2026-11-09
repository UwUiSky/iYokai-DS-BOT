"""
tests/test_embed_avanzati.py
============================
Catalogo #128 B4 (D69): JSON in e out, più embed in un messaggio, bottoni (link e mostra tag), formato V2.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands as ext

import cogs.utility.embed_avanzati as av
import cogs.utility.embed_builder as eb
from core import embed_builder_logic as L
from core.repositories.embed_bottoni_repo import EmbedBottoniRepository
from core.repositories.saved_embed_repo import SavedEmbedRepository
from tests.support.discord_fakes import fake_guild, fake_interaction
from tests.support.percorsi import comando_nel_gruppo


def test_json_nel_formato_di_discord_e_nel_nostro():
    d, e = L.da_testo_json(json.dumps({"embeds": [{"title": "T", "color": 16746496, "fields": [{"name": "a", "value": "b", "inline": True}],
                                                    "image": {"url": "https://x.it/i.png"}, "footer": {"text": "f"}}]}))
    assert e is None and d.color == "#FF8800" and d.fields == (("a", "b", True),) and d.image_url == "https://x.it/i.png" and d.footer == "f"
    nostro = L.a_json(L.DatiEmbed(title="x", fields=(("n", "v", False),)))
    assert L.da_testo_json(nostro)[0].fields == (("n", "v", False),)


def test_json_rifiuti():
    assert L.da_testo_json("non json")[0] is None
    assert L.da_testo_json("[1,2]")[1] is not None
    assert "troppo grande" in L.da_testo_json(" " * (L.MAX_JSON_BYTE + 1))[1]


def test_piu_embed_6000_in_tutto_e_max_10():
    grande = L.DatiEmbed(description="x" * 3500)
    assert L.valida_gruppo([grande]) == []
    assert L.valida_gruppo([grande, grande])  # 7000 in tutto, anche se ognuno è sotto il tetto
    assert L.valida_gruppo([L.DatiEmbed(title="a")] * 11)


def test_v2_conta_componenti_e_testo():
    d = L.DatiEmbed(title="T", description="D", fields=tuple((f"n{i}", "v", False) for i in range(30)))
    d = L.DatiEmbed(title="T", description="D", fields=tuple((f"n{i}", "v", False) for i in range(25)))
    assert any("componenti" in e for e in L.valida_v2(d, 25))
    assert L.valida_v2(L.DatiEmbed(title="T", description="D"), 25) == []
    assert any("testo" in e for e in L.valida_v2(L.DatiEmbed(description="x" * 4001), 0))


def test_regole_dei_bottoni():
    assert L.errore_bottone("link", "Sito", "https://esempio.it") is None
    assert L.errore_bottone("link", "Sito", "ftp://esempio.it")
    assert L.errore_bottone("link", "x" * 81, "https://esempio.it")
    assert L.errore_bottone("tag", "Regole", "regole") is None and L.errore_bottone("tag", "", "regole")
    assert L.errore_bottone("altro", "a", "b")


@pytest.mark.asyncio
async def test_bottoni_repo_tetto_25_scorrimento_e_cascata(clean_db):
    e = SavedEmbedRepository(pool_provider=lambda: clean_db)
    b = EmbedBottoniRepository(pool_provider=lambda: clean_db)
    assert await b.aggiungi(1, "avviso", "link", "x", "https://x.it") == "senza_embed"
    await e.create(1, "avviso", L.a_json(L.DatiEmbed(title="t")), 9)
    for i in range(25):
        assert await b.aggiungi(1, "avviso", "link", f"b{i}", "https://x.it") == "ok"
    assert await b.aggiungi(1, "avviso", "link", "b26", "https://x.it") == "pieno"
    assert await b.togli(1, "avviso", 0) and not await b.togli(1, "avviso", 24)
    elenco = await b.elenco(1, "avviso")
    assert [x.posizione for x in elenco] == list(range(24)) and elenco[0].etichetta == "b1"
    assert (await e.get(1, "avviso")).formato == "classico"
    await e.set_published(1, "avviso", 5, 6, "v2")
    assert (await e.get(1, "avviso")).formato == "v2"
    await e.set_published(1, "avviso", 5, 7)  # senza formato: resta v2
    assert (await e.get(1, "avviso")).formato == "v2"
    await e.delete(1, "avviso")
    assert await b.elenco(1, "avviso") == []  # i bottoni se ne vanno con l'embed


def test_bottone_tag_custom_id_sotto_100():
    b = av.BottoneTag(2**62, "n" * 32, 24, "x")
    assert len(b.item.custom_id) < 100 and av.BottoneTag.__discord_ui_compiled_template__.match(b.item.custom_id)


@pytest.mark.asyncio
async def test_v2_costruito_con_bottoni_e_senza_embed(monkeypatch):
    from core.repositories.embed_bottoni_repo import BottoneEmbed

    monkeypatch.setattr(av.embed_bottoni_repo, "elenco", AsyncMock(return_value=[
        BottoneEmbed(0, "link", "Sito", "https://esempio.it"), BottoneEmbed(1, "tag", "Regole", "regole")]))
    dati = L.DatiEmbed(title="T", description="D", color="#FF0000", thumbnail_url="https://x.it/t.png", image_url="https://x.it/i.png", footer="f")
    c = await av.contenuto_messaggio(1, "avviso", dati, "v2")
    assert set(c) == {"view"} and isinstance(c["view"], discord.ui.LayoutView)
    assert c["view"].to_components()  # si costruisce senza errori
    k = await av.contenuto_messaggio(1, "avviso", dati, "classico")
    assert isinstance(k["embed"], discord.Embed) and len(k["view"].children) == 2


@pytest.mark.asyncio
async def test_pubblica_piu_embed_in_un_messaggio(monkeypatch):
    cog = eb.EmbedBuilderCog(MagicMock())
    monkeypatch.setattr(cog, "_pronto", AsyncMock(return_value=True))
    dati = lambda t: type("S", (), {"data": json.loads(L.a_json(L.DatiEmbed(title=t))), "name": t, "formato": "classico"})()
    monkeypatch.setattr(eb.saved_embed_repo, "get", AsyncMock(side_effect=lambda g, n: dati(n)))
    monkeypatch.setattr(eb.saved_embed_repo, "set_published", AsyncMock())
    monkeypatch.setattr(av.embed_bottoni_repo, "elenco", AsyncMock(return_value=[]))
    canale = MagicMock(spec=discord.TextChannel)
    canale.permissions_for.return_value = discord.Permissions(send_messages=True, embed_links=True)
    canale.send = AsyncMock(return_value=MagicMock(id=5))
    it = fake_interaction()
    await cog.pubblica.callback(cog, it, "a", canale, "b, c", "classico")
    kw = canale.send.await_args.kwargs
    assert len(kw["embeds"]) == 3 and "embed" not in kw
    canale.send.reset_mock()
    await cog.pubblica.callback(cog, it, "a", canale, "b", "v2")  # V2 con altri: rifiutato
    canale.send.assert_not_called()


@pytest.mark.asyncio
async def test_json_import_salva_e_rifiuta_gli_indirizzi_interni(monkeypatch):
    cog = av.EmbedAvanzatiCog(MagicMock())
    crea = AsyncMock(return_value="ok")
    monkeypatch.setattr(av.saved_embed_repo, "create", crea)
    monkeypatch.setattr(av, "url_e_sicuro", AsyncMock(return_value=False))
    it = fake_interaction()
    assert "non è ammesso" in await cog.importa(it, "x", json.dumps({"title": "t", "image": {"url": "http://127.0.0.1/a.png"}}))
    crea.assert_not_called()
    monkeypatch.setattr(av, "url_e_sicuro", AsyncMock(return_value=True))
    assert "importato" in await cog.importa(it, "x", json.dumps({"title": "t"}))
    crea.assert_awaited_once()


@pytest.mark.asyncio
async def test_albero_json_e_bottoni_con_limiti():
    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await av.setup(bot)
    await eb.setup(bot)
    j = comando_nel_gruppo("admin-messaggi", "embed json").to_dict(bot.tree)["options"]
    assert [o["name"] for o in j] == ["azione", "nome", "file", "messaggio"] and j[0]["required"] and not j[2].get("required")
    b = comando_nel_gruppo("admin-messaggi", "embed bottoni").to_dict(bot.tree)["options"]
    obbl = [o.get("required", False) for o in b]
    assert obbl == sorted(obbl, reverse=True)  # nessuna obbligatoria dopo una facoltativa
    assert next(o for o in b if o["name"] == "etichetta")["max_length"] == 80
    p = comando_nel_gruppo("admin-messaggi", "embed pubblica").to_dict(bot.tree)["options"]
    assert {"altri", "formato"} <= {o["name"] for o in p}
