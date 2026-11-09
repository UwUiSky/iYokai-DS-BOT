"""/gif cerca (#131, B10, FUN-056/065): spento di base, solo con una chiave, solo SFW, una pausa tra le ricerche."""
from unittest.mock import AsyncMock

import pytest

import cogs.fun.gif as gifmod
from cogs.fun.entertainment import MODULE_FUN
from core import fun_servizi_logic as servizi
from core import gif_fonti as gf
from core import gif_logic as logica
from core.database import db
from core.gif_fonti import Fonte, Gif, ServizioGif
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

ID = 404


class _Scelta:
    def __init__(self, v):
        self.value = v


def test_voce_di_ricerca_pulisce_aggiunge_tema_e_rifiuta_adulti():
    v = logica.voce_di_ricerca("  gatto   che balla ", "animali")
    assert v.ricerca == "gatto che balla animals" and v.id.startswith("cerca-")
    assert logica.voce_di_ricerca("Gatto che balla").id == logica.voce_di_ricerca("gatto  che   balla").id
    assert logica.voce_di_ricerca("hentai") is None and logica.voce_di_ricerca("   ") is None
    assert len(logica.voce_di_ricerca("x" * 500).ricerca) <= logica.MAX_RICERCA


def test_ricerca_libera_solo_dove_ce_giphy():
    assert logica.ricerca_disponibile(["nekosbest", "giphy"]) and not logica.ricerca_disponibile(["nekosbest", "purrbot"])
    assert gf.FONTI_RICERCA == ("giphy",)


async def test_il_servizio_cerca_solo_con_giphy_e_rating_g():
    visti = []

    async def scarica(url):
        visti.append(url)
        return '{"data": [{"url": "https://giphy.com/gifs/a", "images": {"original": {"url": "https://media.giphy.com/a.gif"}}}]}'

    s = ServizioGif(fonti=[Fonte("nekosbest", gf.FONTI["nekosbest"][0]), Fonte("giphy", gf.FONTI["giphy"][0], "k")], scarica=scarica)
    g = await s.prendi(logica.voce_di_ricerca("gatto"))
    assert g.url.endswith("a.gif") and len(visti) == 1 and "giphy.com/v1/gifs/search" in visti[0] and "rating=g" in visti[0]
    senza = ServizioGif(fonti=[Fonte("nekosbest", gf.FONTI["nekosbest"][0])], scarica=scarica)
    assert await senza.prendi(logica.voce_di_ricerca("gatto")) is None and len(visti) == 1


class _Servizio:
    def __init__(self, nomi=("giphy",), gif=Gif("https://media.giphy.com/a.gif", "GIPHY", "Powered by GIPHY", "https://giphy.com/a")):
        self._nomi, self.gif, self.viste = nomi, gif, []

    def fonti(self):
        return [Fonte(n, "https://x") for n in self._nomi]

    async def prendi(self, voce):
        self.viste.append(voce.ricerca)
        return self.gif


@pytest.fixture
async def cog(monkeypatch, clean_db):
    import core.database as dm
    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    monkeypatch.setattr(gifmod, "servizio_gif", _Servizio())
    yield gifmod.GifCog(bot=None)
    dm.db._modules_cache.clear()
    dm.db._settings_cache.clear()


def _it(u=7):
    it = fake_interaction(guild=fake_guild(ID), user=fake_member(u, "utente"))
    it.delete_original_response = AsyncMock()
    return it


async def test_spento_di_base(cog):
    it = _it()
    await cog.cerca.callback(cog, it, "gatto", None)
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True
    assert gifmod.servizio_gif.viste == []


async def test_acceso_ma_senza_chiave_resta_spento(cog, monkeypatch):
    await db.set_guild_setting(ID, servizi.SETTING_GIF_CERCA, True)
    monkeypatch.setattr(gifmod, "servizio_gif", _Servizio(nomi=("nekosbest",)))
    it = _it()
    await cog.cerca.callback(cog, it, "gatto", None)
    it.response.defer.assert_not_awaited()
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_acceso_con_chiave_manda_gif_con_credito_senza_menzioni(cog):
    await db.set_guild_setting(ID, servizi.SETTING_GIF_CERCA, True)
    it = _it()
    await cog.cerca.callback(cog, it, "@everyone gatto", _Scelta("animali"))
    kw = it.followup.send.await_args.kwargs
    assert kw["embed"].image.url.endswith("a.gif") and "GIPHY" in kw["embed"].footer.text
    assert kw["allowed_mentions"].everyone is False
    assert gifmod.servizio_gif.viste == ["@everyone gatto animals"]


async def test_testo_per_adulti_e_pausa(cog):
    await db.set_guild_setting(ID, servizi.SETTING_GIF_CERCA, True)
    it = _it()
    await cog.cerca.callback(cog, it, "porn", None)
    it.response.defer.assert_not_awaited()
    a, b = _it(9), _it(9)
    await cog.cerca.callback(cog, a, "gatto", None)
    await cog.cerca.callback(cog, b, "cane", None)
    b.response.send_message.assert_awaited()
    assert gifmod.servizio_gif.viste == ["gatto"]
