"""Comandi /fun scegli|numero|testo|casuale|scherzo|effetto (#131) e correzioni sul file."""
import io
from unittest.mock import create_autospec

import discord
import pytest
from PIL import Image

from cogs.fun.entertainment import MODULE_FUN
from cogs.fun.fun_extra import FunExtraCog
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

ID = 101


class _C:
    def __init__(self, value):
        self.value = value
        self.name = value


@pytest.fixture(autouse=True)
async def _attivo(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


@pytest.fixture
def cog():
    return FunExtraCog(bot=None)


def _it():
    return fake_interaction(guild=fake_guild(ID))


def _msg(it):
    return it.response.send_message.await_args


async def test_albero_fun_ha_i_sei_nuovi_e_resta_sotto_25():
    from discord.ext import commands
    import discord as d
    import cogs.fun.entertainment as e, cogs.fun.coin_games as c, cogs.fun.ship_rate as s, cogs.fun.fun_extra as x
    from core.command_groups import GRUPPI

    bot = commands.Bot(command_prefix="!", intents=d.Intents.none())
    for m in (e, c, s, x):
        await m.setup(bot)
    assert {"scegli", "numero", "testo", "casuale", "scherzo", "effetto"} <= percorsi_del_gruppo("fun")
    assert len(GRUPPI["fun"].commands) <= 25
    comando_nel_gruppo("fun", "testo").to_dict(bot.tree)


async def test_modulo_spento_rifiuta(cog):
    await db.set_module_active_for_guild(ID, MODULE_FUN, False)
    it = _it()
    await cog.scegli.callback(cog, it, "a, b")
    assert _msg(it).kwargs["ephemeral"] is True


async def test_scegli_senza_menzioni_e_con_errore(cog):
    it = _it()
    await cog.scegli.callback(cog, it, "@everyone, @here")
    assert _msg(it).kwargs["allowed_mentions"].everyone is False
    it = _it()
    await cog.scegli.callback(cog, it, "una sola")
    assert _msg(it).kwargs["ephemeral"] is True


async def test_numero_intervallo_invertito(cog):
    it = _it()
    await cog.numero.callback(cog, it, 10, 5)
    assert _msg(it).kwargs["ephemeral"] is True
    it = _it()
    await cog.numero.callback(cog, it, 5, 5)
    assert "**5**" in _msg(it).args[0]


async def test_testo_largo(cog):
    it = _it()
    await cog.testo.callback(cog, it, _C("largo"), "ab", " ")
    assert _msg(it).args[0] == "ａｂ"


async def test_scherzo_google_chiede_testo_e_non_pinga(cog):
    it = _it()
    await cog.scherzo.callback(cog, it, _C("google"), fake_member(), None)
    assert _msg(it).kwargs["ephemeral"] is True
    it = _it()
    await cog.scherzo.callback(cog, it, _C("google"), fake_member(), "ciao mondo")
    assert "google.com/search?q=ciao+mondo" in _msg(it).args[0]
    assert _msg(it).kwargs["allowed_mentions"].users is False


async def test_effetto_rip_difer_e_manda_file(cog):
    it = _it()
    it.user = fake_member()
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), "blue").save(buf, format="PNG")
    it.user.display_avatar = create_autospec(discord.Asset, instance=True)
    it.user.display_avatar.read.return_value = buf.getvalue()
    await cog.effetto.callback(cog, it, _C("rip"), None, None, "Mario")
    it.response.defer.assert_awaited_once()
    assert it.followup.send.await_args.kwargs["file"].filename == "rip.png"


# --- correzioni su cogs/fun/entertainment.py ---------------------------

async def test_8ball_non_pinga_e_ha_limite_sulla_domanda():
    from cogs.fun.entertainment import EntertainmentCog
    from core.command_groups import GRUPPI  # noqa: F401
    from discord.ext import commands
    import cogs.fun.entertainment as e

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await e.setup(bot)
    opt = {o.name: o for o in comando_nel_gruppo("fun", "8ball").parameters}["domanda"]
    assert opt.max_value == 300
    cog = EntertainmentCog(bot=None)
    it = _it()
    await cog.eight_ball.callback(cog, it, "@everyone ok?")
    assert _msg(it).kwargs["allowed_mentions"].everyone is False


async def test_meme_testi_con_limite():
    from discord.ext import commands
    import cogs.fun.entertainment as e

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await e.setup(bot)
    par = {o.name: o for o in comando_nel_gruppo("fun", "meme").parameters}
    assert par["top_text"].max_value == 100 and par["bottom_text"].max_value == 100


async def test_dice_con_formula_e_tema_barzelletta():
    from cogs.fun.entertainment import EntertainmentCog

    cog = EntertainmentCog(bot=None)
    it = _it()
    await cog.dice.callback(cog, it, 6, "3d6+2")
    assert "3d6+2" in _msg(it).args[0]
    it = _it()
    await cog.dice.callback(cog, it, 6, "99d6")
    assert _msg(it).kwargs["ephemeral"] is True
    it = _it()
    await cog.joke.callback(cog, it, _C("videogiochi"))
    from core.classic_entertainment_logic import JOKES_TEMATICHE
    assert any(j in _msg(it).args[0] for j in JOKES_TEMATICHE["videogiochi"])
    it = _it()
    await cog.fact.callback(cog, it, _C("gatti"))
    from core.classic_entertainment_logic import FACTS_ANIMALI
    assert any(f in _msg(it).args[0] for f in FACTS_ANIMALI["gatti"])
