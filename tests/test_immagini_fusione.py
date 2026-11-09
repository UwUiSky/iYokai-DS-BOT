"""/immagini fusione (#131, B11, FUN-057): nome fuso, due immagini ufficiali affiancate, nessun file di terzi non ammesso."""
import io
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands
from PIL import Image

import cogs.fun.fusione as mod
from cogs.fun.entertainment import MODULE_FUN
from core import fusione_logic as fl
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

ID = 707
OK = "https://raw.githubusercontent.com/PokeAPI/sprites/master/a.png"


def _png(colore, w=475, h=475):
    f = io.BytesIO()
    Image.new("RGBA", (w, h), colore).save(f, "PNG")
    return f.getvalue()


def test_nome_fuso():
    assert fl.nome_fuso("#25 Pikachu", "#6 Charizard") == "Pikaizard"
    assert fl.nome_fuso("Charmander", "Mew") == "Charmaew"
    assert fl.nome_fuso("A", "B") == "AB"
    assert 0 < len(fl.nome_fuso("x" * 200, "y" * 200)) <= 60


def test_solo_immagini_da_githubusercontent_https():
    assert fl.indirizzo_ammesso(OK) and fl.indirizzo_ammesso("https://githubusercontent.com/x.png")
    for no in ("http://raw.githubusercontent.com/a.png", "https://evil.example/a.png", "https://githubusercontent.com.evil.example/a.png", None, 5):
        assert not fl.indirizzo_ammesso(no)


def test_componi_affianca_due_immagini_png():
    png = fl.componi(_png((255, 0, 0, 255)), _png((0, 0, 255, 255), 100, 300))
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG" and img.width == fl.LATO * 2 + fl.MARGINE * 3 and img.height == fl.LATO + fl.MARGINE * 2
    assert img.getpixel((fl.MARGINE + fl.LATO // 2, img.height // 2))[:3] == (255, 0, 0)
    assert img.getpixel((fl.MARGINE * 2 + fl.LATO + fl.LATO // 2, img.height // 2))[:3] == (0, 0, 255)


class _Cache:
    def __init__(self):
        self.m = {}

    async def leggi(self, k):
        return self.m.get(k)

    async def salva(self, k, v, s):
        self.m[k] = v


async def _una_scheda(monkeypatch, schede):
    from core import schede_giochi_logic as sl

    async def cerca_pokemon(nome, lingua):
        return schede.get(nome.casefold())

    monkeypatch.setattr(sl, "cerca_pokemon", cerca_pokemon)


def _scheda(titolo, url=OK):
    return {"titolo": titolo, "miniatura": url}


async def test_fondi_scarica_solo_ammessi_e_compone(monkeypatch):
    await _una_scheda(monkeypatch, {"pikachu": _scheda("#25 Pikachu"), "charizard": _scheda("#6 Charizard"),
                                    "losco": _scheda("#1 Losco", "https://evil.example/a.png")})
    scaricati = []

    async def scarica(url):
        scaricati.append(url)
        return _png((10, 20, 30, 255)), "image/png"

    nome, png = await fl.fondi("Pikachu", "Charizard", "it", _Cache(), scarica)
    assert nome == "Pikaizard" and png[:4] == b"\x89PNG" and scaricati == [OK, OK]
    assert await fl.fondi("Pikachu", "Losco", "it", _Cache(), scarica) is None and len(scaricati) == 2  # niente scarico da altri domini
    assert await fl.fondi("Pikachu", "inesistente", "it", _Cache(), scarica) is None


async def test_fondi_immagine_rotta_o_assente(monkeypatch):
    await _una_scheda(monkeypatch, {"a": _scheda("#1 Aaa"), "b": _scheda("#2 Bbb")})

    async def rotta(url):
        return b"non e' un'immagine", "image/png"

    async def assente(url):
        return None

    assert await fl.fondi("a", "b", "it", _Cache(), rotta) is None
    assert await fl.fondi("a", "b", "it", _Cache(), assente) is None


@pytest.fixture
async def attivo(monkeypatch, clean_db):
    import core.database as dm
    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


def _it(u=5):
    it = fake_interaction(guild=fake_guild(ID), user=fake_member(u, "u"))
    it.delete_original_response = AsyncMock()
    return it


async def test_albero_immagini_fusione():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await mod.setup(bot)
    assert "fusione" in percorsi_del_gruppo("immagini")
    comando_nel_gruppo("immagini", "fusione").to_dict(bot.tree)


async def test_comando_manda_file_e_senza_menzioni(attivo, monkeypatch):
    cog = mod.FusioneCog(bot=None)
    monkeypatch.setattr(mod.fl, "fondi", AsyncMock(return_value=("Pikaizard", _png((1, 2, 3, 255)))))
    it = _it()
    await cog.fusione.callback(cog, it, "pikachu", "charizard")
    kw = it.followup.send.await_args.kwargs
    assert kw["file"].filename == "fusione.png" and kw["embed"].title == "Pikaizard"
    assert kw["embed"].image.url == "attachment://fusione.png" and kw["allowed_mentions"].everyone is False


async def test_pausa_e_non_trovato(attivo, monkeypatch):
    cog = mod.FusioneCog(bot=None)
    monkeypatch.setattr(mod.fl, "fondi", AsyncMock(return_value=None))
    a, b = _it(9), _it(9)
    await cog.fusione.callback(cog, a, "x", "y")
    a.delete_original_response.assert_awaited()
    assert a.followup.send.await_args.kwargs["ephemeral"] is True
    await cog.fusione.callback(cog, b, "x", "y")
    b.response.send_message.assert_awaited()
    b.response.defer.assert_not_awaited()
