"""B4 di #131 (D70): animali fino a 5 (Uccello, Sorpresa), /immagini foto, /immagini xkcd."""
import io
import json
import random
from types import SimpleNamespace

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from PIL import Image

import cogs.fun.entertainment as ent
from cogs.fun.entertainment import MODULE_FUN, EntertainmentCog
from core import xkcd_fetcher as xk
from core.database import db
from core.image_search_fetcher import ImageSearchFetcherService, RisultatoImmagine
from tests.support.discord_fakes import fake_guild, fake_interaction
from tests.support.percorsi import comando_nel_gruppo

ID = 104
VIGNETTA = {"num": 927, "safe_title": "Standards", "alt": "Fortunately, the charging one...", "img": "https://imgs.xkcd.com/comics/standards.png"}


class _C:
    def __init__(self, value, name=None):
        self.value, self.name = value, name or value


# --- xkcd -----------------------------------------------------------------

def test_interpreta_vignetta_valida_e_rifiuti():
    v = xk.interpreta(json.dumps(VIGNETTA))
    assert v and v.numero == 927 and v.pagina == "https://xkcd.com/927/"
    for guasto in (
        "non json", "[]", json.dumps({**VIGNETTA, "num": 0}), json.dumps({**VIGNETTA, "img": "https://evil.example/x.png"}),
        json.dumps({**VIGNETTA, "img": "http://imgs.xkcd.com/x.png"}), json.dumps({**VIGNETTA, "img": "https://imgs.xkcd.com.evil.io/x.png"}),
        json.dumps({k: v for k, v in VIGNETTA.items() if k != "safe_title"}), None,
    ):
        assert xk.interpreta(guasto) is None


async def test_servizio_xkcd_url_cache_e_scadenza():
    chiamate, ora = [], [0.0]

    async def scarica(url, max_bytes):
        chiamate.append((url, max_bytes))
        return json.dumps(VIGNETTA) if "927" in url or url == xk.URL_ULTIMA else None

    s = xk.XkcdService(scarica, lambda: ora[0])
    assert (await s.vignetta()).numero == 927
    assert (await s.vignetta(927)).numero == 927
    await s.vignetta(927)
    assert [u for u, _ in chiamate] == [xk.URL_ULTIMA, "https://xkcd.com/927/info.0.json"]
    assert all(b == xk.MAX_BYTE for _, b in chiamate)
    ora[0] = xk.SECONDI_CACHE_ULTIMA + 1
    await s.vignetta()
    assert len(chiamate) == 3
    assert await s.vignetta(404) is None  # non esiste: nessuna eccezione, nessuna cache
    assert await s.vignetta(404) is None and len(chiamate) == 5


# --- più foto da Pixabay --------------------------------------------------

@pytest.fixture
async def pixabay_finto():
    png = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(png, format="PNG")

    async def cerca(request):
        base = f"http://127.0.0.1:{request.url.port}"
        hits = [{"webformatURL": f"{base}/img/{i}", "pageURL": f"https://pixabay.com/p/{i}/"} for i in range(6)]
        return web.json_response({"hits": hits})

    async def img(request):
        return web.Response(body=png.getvalue(), content_type="image/png")

    app = web.Application()
    app.router.add_get("/api/", cerca)
    app.router.add_get("/img/{n}", img)
    server = TestServer(app)
    await server.start_server()
    try:
        yield server
    finally:
        await server.close()


async def test_fetch_immagini_distinte_e_con_tetto(pixabay_finto, monkeypatch):
    base = str(pixabay_finto.make_url("/api/"))
    s = ImageSearchFetcherService(search_url=base, domini_immagine=("127.0.0.1",))
    try:
        trovate = await s.fetch_immagini("k", "bird", random.Random(1), 4)
        assert len(trovate) == 4 and len({t.pagina for t in trovate}) == 4
        assert await s.fetch_immagini("", "bird", random.Random(1), 4) == []
        dimensione = len(trovate[0].dati)
        monkeypatch.setattr("core.image_search_fetcher.MAX_BYTE_TOTALI", dimensione * 2 + 1)
        assert len(await s.fetch_immagini("k", "bird", random.Random(1), 5)) == 2
    finally:
        await s._get_session().close()


# --- comandi --------------------------------------------------------------

@pytest.fixture(autouse=True)
async def _db(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


def _it():
    return fake_interaction(guild=fake_guild(ID))


class _Cani:
    def __init__(self):
        self.richieste = []

    async def fetch_image_url(self, specie):
        self.richieste.append(specie)
        return f"https://img.example/{specie}{len(self.richieste)}.jpg"


class _Uccelli:
    def __init__(self, quanti=3):
        self.quanti, self.chiamate = quanti, []

    async def fetch_immagini(self, chiave, query, rng, quante):
        self.chiamate.append((query, quante))
        return [RisultatoImmagine(b"png", "jpg", f"https://pixabay.com/p/{i}/") for i in range(min(quante, self.quanti))]

    async def fetch_image(self, chiave, query, rng):
        self.chiamate.append((query, 1))
        return RisultatoImmagine(b"png", "jpg", "https://pixabay.com/p/x/")


async def test_animal_cinque_cani_cinque_embed(monkeypatch):
    cani = _Cani()
    monkeypatch.setattr(ent, "animal_fetcher", cani)
    cog = EntertainmentCog(bot=None)
    it = _it()
    await cog.animal.callback(cog, it, _C("dog", "Cane"), 5)
    embeds = it.followup.send.await_args.kwargs["embeds"]
    assert len(embeds) == 5 and embeds[0].title == "Cane casuale" and embeds[1].title is None
    assert cani.richieste == ["dog"] * 5


async def test_animal_uccello_usa_pixabay_con_file_e_senza_chiave_avvisa(monkeypatch):
    uccelli = _Uccelli()
    monkeypatch.setattr(ent, "image_search_fetcher", uccelli)
    monkeypatch.setattr(ent, "config", SimpleNamespace(PIXABAY_API_KEY=""))
    cog = EntertainmentCog(bot=None)
    it = _it()
    await cog.animal.callback(cog, it, _C("bird", "Uccello"), 2)
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True and not uccelli.chiamate
    monkeypatch.setattr(ent, "config", SimpleNamespace(PIXABAY_API_KEY="k"))
    it = _it()
    await cog.animal.callback(cog, it, _C("bird", "Uccello"), 2)
    invio = it.followup.send.await_args.kwargs
    assert uccelli.chiamate == [("bird", 2)] and len(invio["embeds"]) == 2 and len(invio["files"]) == 2
    assert invio["embeds"][0].image.url == "attachment://uccello0.jpg"


async def test_animal_sorpresa_sceglie_tra_le_quattro(monkeypatch):
    cani, uccelli = _Cani(), _Uccelli(5)
    monkeypatch.setattr(ent, "animal_fetcher", cani)
    monkeypatch.setattr(ent, "image_search_fetcher", uccelli)
    monkeypatch.setattr(ent, "config", SimpleNamespace(PIXABAY_API_KEY="k"))
    cog = EntertainmentCog(bot=None)
    cog._rng = random.Random(3)
    it = _it()
    await cog.animal.callback(cog, it, _C("surprise", "Sorpresa"), 5)
    assert set(cani.richieste) <= {"dog", "cat", "fox"}
    totale = len(cani.richieste) + (uccelli.chiamate[0][1] if uccelli.chiamate else 0)
    assert totale == 5


async def test_foto_usa_query_curata_con_pausa(monkeypatch):
    uccelli = _Uccelli()
    monkeypatch.setattr(ent, "image_search_fetcher", uccelli)
    monkeypatch.setattr(ent, "config", SimpleNamespace(PIXABAY_API_KEY="k"))
    cog = EntertainmentCog(bot=None)
    it = _it()
    await cog.foto.callback(cog, it, _C("cibo", "Cibo"))
    assert uccelli.chiamate[0][0] in ent.QUERY_FOTO["cibo"]
    assert it.followup.send.await_args.kwargs["embed"].image.url.startswith("attachment://pixabay")
    it = _it()
    await cog.foto.callback(cog, it, _C("buonumore", "Buonumore"))  # entro 10 secondi: pausa
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True and len(uccelli.chiamate) == 1


async def test_xkcd_embed_con_credito_e_non_trovata(monkeypatch):
    class Finto:
        async def vignetta(self, numero):
            return xk.interpreta(json.dumps(VIGNETTA)) if numero in (None, 927) else None

    monkeypatch.setattr(ent, "xkcd_service", Finto())
    cog = EntertainmentCog(bot=None)
    it = _it()
    await cog.xkcd.callback(cog, it, 927)
    e = it.followup.send.await_args.kwargs["embed"]
    assert e.title == "#927 · Standards" and e.url == "https://xkcd.com/927/" and "CC BY-NC" in e.footer.text
    assert e.image.url == VIGNETTA["img"]
    it = _it()
    await cog.xkcd.callback(cog, it, 404)
    assert it.followup.send.await_args.kwargs["ephemeral"] is True


async def test_albero_scelte_e_opzioni():
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await ent.setup(bot)
    a = comando_nel_gruppo("immagini", "animal")
    par = {o.name: o for o in a.parameters}
    assert len(par["specie"].choices) == 5 and (par["quante"].min_value, par["quante"].max_value) == (1, 5)
    assert par["quante"].required is False and par["specie"].required is True
    x = {o.name: o for o in comando_nel_gruppo("immagini", "xkcd").parameters}["numero"]
    assert x.required is False and x.min_value == 1
    assert len({o.name for o in comando_nel_gruppo("immagini", "foto").parameters}) == 1
