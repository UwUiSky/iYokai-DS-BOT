"""
tests/test_user_app_divertimento.py
===================================
SPEC B.7 (#107): `/divertimento` di iYokai App, gli stessi giochi e le stesse immagini di `/fun`.
"""

import io
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

import cogs.user_app.divertimento as div
from tests.support.discord_fakes import fake_interaction, fake_member


@pytest.fixture
def cog():
    c = div.DivertimentoCog(MagicMock(tree=MagicMock()))
    c._rng = random.Random(1)
    return c


def _i(user_id=7):
    return fake_interaction(user=fake_member(user_id=user_id))


def _testo(i):
    return i.response.send_message.await_args.args[0]


def _png():
    buffer = io.BytesIO()
    Image.new("RGB", (120, 120), (30, 60, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_il_gruppo_ha_i_17_comandi_e_sta_nei_limiti(cog):
    nomi = {c.name for c in div.DivertimentoCog.divertimento.commands}
    assert len(nomi) == 17 <= 25
    assert {"moneta", "dado", "forbici", "palla8", "barzelletta", "citazione", "curiosita", "animale", "immagine",
            "meme", "effetto", "ship", "valuta", "scegli", "numero", "testo", "casuale"} == nomi


async def test_giochi_pubblici_di_base_e_privati_a_richiesta(cog):
    i = _i()
    await cog.moneta.callback(cog, i, False)
    assert ("TESTA" in _testo(i) or "CROCE" in _testo(i)) and i.response.send_message.await_args.kwargs["ephemeral"] is False
    i = _i()
    await cog.moneta.callback(cog, i, True)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    assert i.response.send_message.await_args.kwargs["allowed_mentions"].users is False


async def test_dado_facce_e_formula(cog):
    i = _i()
    await cog.dado.callback(cog, i, 20, None, False)
    assert "d20" in _testo(i)
    i = _i()
    await cog.dado.callback(cog, i, 6, "2d6+3", False)
    assert "2d6+3" in _testo(i) and "=" in _testo(i)
    i = _i()
    await cog.dado.callback(cog, i, 6, "xyz", False)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_forbici_scegli_numero_testo(cog):
    i = _i()
    await cog.forbici.callback(cog, i, discord.app_commands.Choice(name="Sasso", value="sasso"), False)
    assert "vs" in _testo(i)
    i = _i()
    await cog.scegli.callback(cog, i, "pizza, sushi, kebab", False)
    assert any(x in _testo(i) for x in ("pizza", "sushi", "kebab"))
    i = _i()
    await cog.scegli.callback(cog, i, "solo", False)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    i = _i()
    await cog.numero.callback(cog, i, 10, 1, False)
    assert "minimo" in _testo(i)
    i = _i()
    await cog.numero.callback(cog, i, 5, 5, False)
    assert "**5**" in _testo(i)
    i = _i()
    await cog.testo.callback(cog, i, discord.app_commands.Choice(name="Largo", value="largo"), "ciao", False)
    assert _testo(i) == "ｃｉａｏ"


async def test_ship_e_valuta_senza_allarmare_nessuno(cog):
    i = _i()
    await cog.ship.callback(cog, i, SimpleNamespace(id=1, display_name="A"), SimpleNamespace(id=2, display_name="B"), False)
    assert "A" in i.response.send_message.await_args.kwargs["embed"].description
    i = _i()
    await cog.valuta.callback(cog, i, "la pizza", False)
    assert "/10" in i.response.send_message.await_args.kwargs["embed"].description


async def test_meme_serve_un_testo_e_controlla_l_allegato(cog):
    i = _i()
    await cog.meme.callback(cog, i, "", "", None, None, False)
    assert "almeno un testo" in _testo(i)
    pdf = MagicMock(spec=discord.Attachment)
    pdf.content_type, pdf.size = "application/pdf", 10
    i = _i()
    await cog.meme.callback(cog, i, "ciao", "", pdf, None, False)
    assert "non è un'immagine" in _testo(i)
    grande = MagicMock(spec=discord.Attachment)
    grande.content_type, grande.size = "image/png", 50 * 1024 * 1024
    i = _i()
    await cog.meme.callback(cog, i, "ciao", "", grande, None, False)
    assert "troppo grande" in _testo(i)


async def test_meme_ed_effetto_producono_un_file(cog):
    allegato = MagicMock(spec=discord.Attachment)
    allegato.content_type, allegato.size = "image/png", 100
    allegato.read = AsyncMock(return_value=_png())
    i = _i()
    await cog.meme.callback(cog, i, "ciao", "mondo", allegato, None, True)
    assert i.followup.send.await_args.kwargs["file"].filename == "meme.png"
    assert i.followup.send.await_args.kwargs["ephemeral"] is True
    i = _i()
    i.user.display_avatar.read = AsyncMock(return_value=_png())
    await cog.effetto.callback(cog, i, discord.app_commands.Choice(name="Lapide", value="rip"), None, None, "Yo", False)
    assert i.followup.send.await_args.kwargs["file"].filename == "rip.png"


async def test_immagine_non_scaricabile_e_non_elaborabile(cog):
    allegato = MagicMock(spec=discord.Attachment)
    allegato.content_type, allegato.size = "image/png", 100
    allegato.read = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=404), "x"))
    i = _i()
    await cog.meme.callback(cog, i, "ciao", "", allegato, None, False)
    assert "scaricare" in i.followup.send.await_args.args[0]
    allegato.read = AsyncMock(return_value=b"non e' un'immagine")
    i = _i()
    await cog.meme.callback(cog, i, "ciao", "", allegato, None, False)
    assert "elaborare" in i.followup.send.await_args.args[0]


async def test_animale_e_ricerca_immagine(cog, monkeypatch):
    monkeypatch.setattr(div.animal_fetcher, "fetch_image_url", AsyncMock(return_value="https://x/cane.png"))
    i = _i()
    await cog.animale.callback(cog, i, discord.app_commands.Choice(name="Cane", value="dog"), False)
    assert i.followup.send.await_args.kwargs["embed"].image.url == "https://x/cane.png"
    monkeypatch.setattr(div.animal_fetcher, "fetch_image_url", AsyncMock(return_value=None))
    i = _i()
    await cog.animale.callback(cog, i, discord.app_commands.Choice(name="Cane", value="dog"), False)
    assert "Riprova" in i.followup.send.await_args.args[0]

    monkeypatch.setattr(div, "config", SimpleNamespace(PIXABAY_API_KEY=""))
    i = _i()
    await cog.immagine.callback(cog, i, "gatti", False)
    assert "non è attiva" in _testo(i)
    monkeypatch.setattr(div, "config", SimpleNamespace(PIXABAY_API_KEY="chiave"))
    risultato = SimpleNamespace(dati=_png(), estensione="png", pagina="https://pixabay.com/x")
    monkeypatch.setattr(div.image_search_fetcher, "fetch_image", AsyncMock(return_value=risultato))
    i = _i()
    await cog.immagine.callback(cog, i, "gatti", False)
    assert i.followup.send.await_args.kwargs["file"].filename == "pixabay.png"
    i = _i()
    await cog.immagine.callback(cog, i, "gatti", False)  # troppo presto: pausa di 10 secondi
    assert "Aspetta" in _testo(i)


async def test_il_cog_non_si_carica_sul_bot_principale():
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await div.setup(bot)
    assert bot.cogs == {}
    await bot.close()
