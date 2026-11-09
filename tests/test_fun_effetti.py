"""B5 di #131 (D70): nuovi effetti sulle immagini e tre scherzi."""
import io

import pytest
from PIL import Image, ImageChops

from cogs.fun.entertainment import MODULE_FUN
from cogs.fun.fun_extra import _EFFETTI, FunExtraCog
from core import fun_extra_logic as lg
from core import image_effects_logic as ef
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo

ID = 105
NUOVI = ("pingato", "specchio", "seppia", "pixel", "cornice", "vignetta", "neon")


def _png(colore="blue", lato=64):
    img = Image.new("RGB", (lato, lato), colore)
    img.paste(Image.new("RGB", (lato // 2, lato // 2), "red"), (0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _C:
    def __init__(self, value):
        self.value = value
        self.name = value


@pytest.mark.parametrize("tipo", NUOVI)
def test_effetto_produce_png_quadrato_leggero_e_rifiuta_file_rotti(tipo):
    nome, fn, vuole_nome = _EFFETTI[tipo]
    args = ("Mario",) if vuole_nome else ()
    png = fn(_png(), *args)
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG" and img.width == ef.LATO and img.height >= ef.LATO
    assert len(png) < 1_000_000
    assert fn(b"non sono un'immagine", *args) is None


def test_effetti_cambiano_davvero_l_immagine():
    base = Image.open(io.BytesIO(_png())).convert("RGB").resize((ef.LATO, ef.LATO))
    for tipo in ("specchio", "seppia", "pixel", "cornice", "vignetta", "neon"):
        out = Image.open(io.BytesIO(_EFFETTI[tipo][1](_png()))).convert("RGB")
        assert ImageChops.difference(base, out).getbbox() is not None, tipo


def test_specchio_e_simmetrico_e_pingato_ha_il_nome():
    out = Image.open(io.BytesIO(ef.effetto_specchio(_png()))).convert("RGB")
    assert ImageChops.difference(out.crop((0, 0, 256, 512)), out.crop((256, 0, 512, 512)).transpose(Image.FLIP_LEFT_RIGHT)).getbbox() is None
    assert Image.open(io.BytesIO(ef.effetto_pingato(_png(), "x" * 100))).height == ef.LATO + 110


def test_logica_scherzi():
    assert lg.tutto_in_spoiler("ciao  a | tutti") == "||ciao|| ||a|| ||tutti||"
    assert lg.barra_caricamento().count("▓") == 9 and len(lg.barra_caricamento()) == 10


@pytest.fixture(autouse=True)
async def _db(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


def _it():
    it = fake_interaction(guild=fake_guild(ID))
    it.user = fake_member()
    return it


async def test_scherzi_nuovi_senza_ping():
    cog = FunExtraCog(bot=None)
    bersaglio = fake_member()
    it = _it()
    await cog.scherzo.callback(cog, it, _C("spoiler"), bersaglio, None)
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True
    it = _it()
    await cog.scherzo.callback(cog, it, _C("spoiler"), bersaglio, "@everyone ciao")
    inviato = it.response.send_message.await_args
    assert "||@everyone||" in inviato.args[0] and inviato.kwargs["allowed_mentions"].everyone is False
    for tipo, atteso in (("caricamento", "99%"), ("brindisi", "🥂")):
        it = _it()
        await cog.scherzo.callback(cog, it, _C(tipo), bersaglio, None)
        assert atteso in it.response.send_message.await_args.args[0]
        assert it.response.send_message.await_args.kwargs["allowed_mentions"].users is False


async def test_effetto_nuovo_manda_file(monkeypatch):
    from unittest.mock import create_autospec

    import discord

    cog = FunExtraCog(bot=None)
    it = _it()
    it.user.display_avatar = create_autospec(discord.Asset, instance=True)
    it.user.display_avatar.read.return_value = _png()
    await cog.effetto.callback(cog, it, _C("pingato"), None, None, "Luca")
    assert it.followup.send.await_args.kwargs["file"].filename == "pingato.png"


async def test_albero_effetti_e_scherzi_nei_limiti():
    import discord
    from discord.ext import commands

    import cogs.fun.fun_extra as x

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await x.setup(bot)
    tipo = {o.name: o for o in comando_nel_gruppo("immagini", "effetto").parameters}["tipo"]
    assert 4 < len(tipo.choices) <= 25 and {c.value for c in tipo.choices} == set(_EFFETTI)
    assert all(len(c.name) <= 100 for c in tipo.choices)
    sc = {o.name: o for o in comando_nel_gruppo("fun", "scherzo").parameters}
    assert len(sc["tipo"].choices) == 6 and sc["testo"].required is False and sc["testo"].max_value == 100
