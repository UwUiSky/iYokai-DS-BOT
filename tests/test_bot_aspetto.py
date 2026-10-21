"""
tests/test_bot_aspetto.py
=========================
Aspetto del bot per server (CFG-021, CFG-030, #122): campi toccati o tolti,
controllo delle immagini, premium, limite sui cambi di immagine, errori di
Discord, e il comando `/admin premium aspetto`.
"""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands
from PIL import Image

import core.premium as premium_module
from core import bot_aspetto
from core.web_panel_logic import LimiteFrequenza
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

pytestmark = pytest.mark.asyncio


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def _guild():
    g = fake_guild(guild_id=600)
    g.me = SimpleNamespace(edit=AsyncMock(), nick=None, guild_avatar=None, guild_banner=None)
    return g


@pytest.fixture(autouse=True)
def premium(monkeypatch):
    stato = SimpleNamespace(attivo=True)

    async def _accesso(guild_id, modulo, bot=None):
        assert modulo == bot_aspetto.MODULO_ASPETTO
        return stato.attivo

    monkeypatch.setattr(premium_module, "guild_has_premium_access", _accesso)
    monkeypatch.setattr(bot_aspetto, "_limite_immagini", LimiteFrequenza(4, 600))
    return stato


async def test_cambia_solo_i_campi_scelti():
    g = _guild()
    dati = _png()
    assert await bot_aspetto.applica_aspetto(None, g, 7, avatar=dati, bio="  Ciao  ", banner=None) == "asp_ok"
    kwargs = g.me.edit.call_args.kwargs
    assert kwargs["avatar"] == dati and kwargs["bio"] == "Ciao" and kwargs["banner"] is None
    assert "nick" not in kwargs and "7" in kwargs["reason"]
    assert await bot_aspetto.applica_aspetto(None, g, 7) == "asp_niente"


async def test_nickname_libero_il_resto_premium(premium):
    premium.attivo = False
    g = _guild()
    assert await bot_aspetto.applica_aspetto(None, g, 7, nick=" Yokai ") == "asp_ok"
    assert g.me.edit.call_args.kwargs["nick"] == "Yokai"
    g.me.edit.reset_mock()
    assert await bot_aspetto.applica_aspetto(None, g, 7, bio="x") == "asp_richiede_premium"
    assert await bot_aspetto.applica_aspetto(None, g, 7, avatar=None) == "asp_richiede_premium"
    g.me.edit.assert_not_awaited()


async def test_immagini_e_testi_rifiutati():
    g = _guild()
    assert await bot_aspetto.applica_aspetto(None, g, 7, avatar=b"non sono un'immagine") == "asp_immagine_non_valida"
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, format="BMP")
    assert await bot_aspetto.applica_aspetto(None, g, 7, banner=buffer.getvalue()) == "asp_immagine_non_valida"
    grande = b"\0" * (bot_aspetto.MAX_IMMAGINE + 1)
    assert await bot_aspetto.applica_aspetto(None, g, 7, avatar=grande) == "asp_immagine_grande"
    assert await bot_aspetto.applica_aspetto(None, g, 7, bio="x" * 191) == "asp_testo_lungo"
    assert await bot_aspetto.applica_aspetto(None, g, 7, nick="x" * 33) == "asp_testo_lungo"
    g.me.edit.assert_not_awaited()


async def test_quattro_immagini_ogni_dieci_minuti_e_togliere_e_sempre_libero():
    g = _guild()
    for _ in range(4):
        assert await bot_aspetto.applica_aspetto(None, g, 7, avatar=_png()) == "asp_ok"
    assert await bot_aspetto.applica_aspetto(None, g, 7, avatar=_png()) == "asp_attendi"
    assert await bot_aspetto.applica_aspetto(None, g, 7, avatar=None) == "asp_ok"


async def test_errori_di_discord():
    g = _guild()
    risposta = MagicMock(status=403)
    g.me.edit.side_effect = discord.Forbidden(risposta, "no")
    assert await bot_aspetto.applica_aspetto(None, g, 7, nick="A") == "cfg_nick_permesso"
    assert await bot_aspetto.applica_aspetto(None, g, 7, bio="A") == "asp_errore"
    g.me.edit.side_effect = discord.HTTPException(MagicMock(status=400), "no")
    assert await bot_aspetto.applica_aspetto(None, g, 7, bio="A") == "asp_errore"


async def test_comando_aspetto():
    from cogs.utility.marchio import MarchioCog

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = MarchioCog(bot)
    g = _guild()

    def nuova():
        i = fake_interaction(guild=g, user=fake_member(77))
        i.locale = discord.Locale.italian
        return i

    allegato = SimpleNamespace(size=100, read=AsyncMock(return_value=_png()))
    i = nuova()
    await cog.aspetto.callback(cog, i, allegato, None, "Il bot del server", None)
    assert "Fatto" in i.followup.send.call_args.args[0]
    assert set(g.me.edit.call_args.kwargs) == {"avatar", "bio", "reason"}

    i = nuova()
    await cog.aspetto.callback(cog, i, None, None, None, app_commands.Choice(name="tutto", value="tutto"))
    kwargs = g.me.edit.call_args.kwargs
    assert kwargs["avatar"] is None and kwargs["banner"] is None and kwargs["bio"] is None

    grande = SimpleNamespace(size=bot_aspetto.MAX_IMMAGINE + 1, read=AsyncMock())
    i = nuova()
    await cog.aspetto.callback(cog, i, None, grande, None, None)
    assert "8 MB" in i.followup.send.call_args.args[0]
    grande.read.assert_not_awaited()

    # L'allegato non si scarica (scaduto, Discord giù): un messaggio, niente eccezione, niente modifica.
    g.me.edit.reset_mock()
    rotto = SimpleNamespace(size=100, read=AsyncMock(side_effect=discord.HTTPException(MagicMock(status=503), "giù")))
    i = nuova()
    await cog.aspetto.callback(cog, i, rotto, None, None, None)
    assert "scaricare l'immagine" in i.followup.send.call_args.args[0]
    g.me.edit.assert_not_awaited()
