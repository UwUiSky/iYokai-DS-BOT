"""GIF (D127, #131): Tenor, accensione con la chiave, ordine, tetti di quota e le 10 voci che prima non avevano fonte. Nessuna rete."""
import json
import random

import pytest

from core import gif_catalogo as catalogo
from core import gif_fonti as f

DIECI = ("FUN-101", "FUN-104", "FUN-105", "FUN-115", "FUN-127", "FUN-128", "FUN-132", "FUN-133", "FUN-134", "FUN-135")


def _voce(codice):
    return next(v for v in catalogo.tutte() if v.fun == codice)


def _fonte(nome, chiave=""):
    return f.Fonte(nome, f.FONTI[nome][0], chiave)


class _Rete:
    def __init__(self, risposte):
        self.risposte = risposte
        self.chiamate = []

    async def __call__(self, url):
        self.chiamate.append(url)
        for chiave, testo in self.risposte.items():
            if chiave in url:
                return testo
        return None


TENOR = json.dumps({"results": [{"itemurl": "https://tenor.com/view/x-1", "media_formats": {
    "mediumgif": {"url": "https://media.tenor.com/abc/x.gif"}, "gif": {"url": "https://evil.example/x.gif"}}}]})
GIPHY = json.dumps({"data": [{"url": "https://giphy.com/gifs/a", "images": {"downsized": {"url": "https://media1.giphy.com/a.gif"}}}]})


def test_le_fonti_con_chiave_si_accendono_da_sole_e_si_spengono_con_l_interruttore():
    assert [x.nome for x in f.leggi_fonti({})] == ["nekosbest", "purrbot", "waifupics", "otakugifs"]
    nomi = [x.nome for x in f.leggi_fonti({"GIF_TENOR_KEY": "k", "GIF_GIPHY_KEY": "g"})]
    assert nomi[-2:] == ["giphy", "tenor"]  # dopo le fonti per categoria
    assert "tenor" not in [x.nome for x in f.leggi_fonti({"GIF_TENOR_KEY": "k", "GIF_TENOR_ATTIVO": "no"})]
    assert "tenor" not in [x.nome for x in f.leggi_fonti({"GIF_TENOR_URL": "https://evil.example"})]
    assert "tenor" not in [x.nome for x in f.leggi_fonti({"GIF_TENOR_KEY": "k", "GIF_TENOR_URL": "http://tenor.googleapis.com/v2"})]
    assert f.FONTI_RICERCA == ("giphy", "tenor")


def test_tenor_chiede_il_filtro_alto_solo_sfw_e_scarta_i_domini_estranei():
    url = f._richiesta(_fonte("tenor", "k"), _voce("FUN-101"))
    assert url.startswith("https://tenor.googleapis.com/v2/search?") and "contentfilter=high" in url and "key=k" in url
    cattiva = catalogo.Voce("x", "", "cerca", {}, (), "hentai", {})
    assert f._richiesta(_fonte("tenor", "k"), cattiva) is None
    gif = f.leggi_risposta("tenor", TENOR)
    assert [g.url for g in gif] == ["https://media.tenor.com/abc/x.gif"] and gif[0].fonte == "Tenor"
    assert gif[0].link == "https://tenor.com/view/x-1" and gif[0].dettaglio == f.TENOR_CREDITO
    fuori = json.dumps({"results": [{"media_formats": {"gif": {"url": "https://evil.example/x.gif"}}}]})
    assert f.leggi_risposta("tenor", fuori) == [] and f.leggi_risposta("tenor", "[]") == [] and f.leggi_risposta("tenor", "no") == []


def test_canta_ha_una_categoria_vera_su_otakugifs():
    voce = _voce("FUN-104")
    assert voce.fonti == {"otakugifs": "sing"}
    assert f._richiesta(_fonte("otakugifs"), voce) == "https://api.otakugifs.xyz/gif?reaction=sing&format=gif"


@pytest.mark.parametrize("codice", DIECI)
async def test_ogni_voce_ha_almeno_una_fonte_reale_con_risposte_finte(codice):
    rete = _Rete({"otakugifs": json.dumps({"url": "https://media.otakugifs.xyz/s.gif"}), "giphy": GIPHY, "tenor": TENOR})
    voce = _voce(codice)
    tutte = f.ServizioGif([_fonte("otakugifs"), _fonte("giphy", "g"), _fonte("tenor", "k")], rete, random.Random(1))
    assert await tutte.prendi(voce) is not None
    # senza chiavi: solo la voce con categoria risponde, le altre restano con la sola frase
    senza = f.ServizioGif([_fonte("otakugifs")], _Rete({"otakugifs": json.dumps({"url": "https://media.otakugifs.xyz/s.gif"})}))
    assert (await senza.prendi(voce) is not None) == (codice == "FUN-104")


async def test_la_categoria_viene_prima_della_ricerca_e_la_ricerca_fa_da_ripiego():
    hug = catalogo.trova("azione", "abbraccia")
    rete = _Rete({"purrbot": json.dumps({"link": "https://purrbot.site/a.gif"}), "giphy": GIPHY, "tenor": TENOR})
    s = f.ServizioGif([_fonte("purrbot"), _fonte("giphy", "g"), _fonte("tenor", "k")], rete, random.Random(1))
    for _ in range(4):
        assert (await s.prendi(hug)).fonte == "purrbot.site"
    assert not any("giphy" in u or "tenor" in u for u in rete.chiamate)
    muta = _Rete({"giphy": None, "tenor": TENOR})
    s2 = f.ServizioGif([_fonte("purrbot"), _fonte("giphy", "g"), _fonte("tenor", "k")], muta, random.Random(1))
    assert (await s2.prendi(hug)).fonte == "Tenor"


def test_tetto_di_quota_per_fonte_con_valore_dal_file():
    assert f.quota_oraria("giphy", {}) == 90 and f.quota_oraria("giphy", {"GIF_GIPHY_QUOTA_ORA": "10"}) == 10
    assert f.quota_oraria("giphy", {"GIF_GIPHY_QUOTA_ORA": "zero"}) == 90 and f.quota_oraria("sconosciuta", {}) == 300


async def test_oltre_il_tetto_orario_la_fonte_non_viene_chiamata_poi_riprende():
    t = [0.0]
    rete = _Rete({"tenor": TENOR})
    voce = _voce("FUN-101")
    s = f.ServizioGif([_fonte("tenor", "k")], rete, random.Random(1), adesso=lambda: t[0])
    tetto = f.quota_oraria("tenor")
    s._richieste["tenor"] = [0.0] * tetto
    assert await s.prendi(voce) is None and rete.chiamate == []
    t[0] = 3601
    assert await s.prendi(voce) is not None and len(rete.chiamate) == 1


@pytest.mark.parametrize("nome, risposta", [
    ("nekosbest", json.dumps({"results": [{"url": "https://nekos.best/api/v2/hug/1.gif", "anime_name": "A"}]})),
    ("purrbot", json.dumps({"link": "https://purrbot.site/img/sfw/hug/gif/1.gif"})),
    ("waifupics", json.dumps({"url": "https://i.waifu.pics/1.gif"})),
    ("otakugifs", json.dumps({"url": "https://media.otakugifs.xyz/1.gif"})),
    ("nekoslife", json.dumps({"url": "https://nekos.life/img/1.gif"})),
    ("giphy", GIPHY), ("tenor", TENOR),
])
async def test_ogni_servizio_risponde_con_la_sua_risposta_finta(nome, risposta):
    hug = catalogo.trova("azione", "abbraccia")
    if nome == "nekoslife":
        hug = catalogo.Voce("h", "", "azione", {}, (), "anime hug", {"nekoslife": "hug"})
    s = f.ServizioGif([_fonte(nome, "k")], _Rete({"": risposta}), random.Random(1))
    assert await s.prendi(hug) is not None
