"""Fonti delle GIF (D70, #131): lettura della configurazione, richieste SFW, risposte, cache e ripiego. Nessuna rete."""
import json
import random

import pytest

from core import gif_catalogo as catalogo
from core import gif_fonti as f

HUG = catalogo.trova("azione", "abbraccia")


def _fonte(nome):
    return f.Fonte(nome, f.FONTI[nome][0], "chiave" if nome == "giphy" else "")


def test_valori_iniziali_e_interruttori():
    assert [x.nome for x in f.leggi_fonti({})] == ["nekosbest", "purrbot", "waifupics", "otakugifs"]
    spenta = f.leggi_fonti({"GIF_NEKOSBEST_ATTIVO": "no", "GIF_ORDINE": "otakugifs,purrbot"})
    assert [x.nome for x in spenta] == ["otakugifs", "purrbot", "waifupics"]


def test_giphy_serve_la_chiave_e_l_indirizzo_deve_essere_https():
    assert "giphy" not in [x.nome for x in f.leggi_fonti({"GIF_GIPHY_ATTIVO": "si"})]
    con = f.leggi_fonti({"GIF_GIPHY_ATTIVO": "si", "GIF_GIPHY_KEY": "k"})
    assert "giphy" in [x.nome for x in con]
    assert "purrbot" not in [x.nome for x in f.leggi_fonti({"GIF_PURRBOT_URL": "http://x.example"})]


def test_l_ambiente_vince_sul_file(tmp_path):
    file = tmp_path / "gif.env"
    file.write_text("GIF_NEKOSBEST_ATTIVO=no\nGIF_PURRBOT_ATTIVO=no\nALTRO=1\n", encoding="utf-8")
    env = f.env_con_file({"GIF_PURRBOT_ATTIVO": "si"}, file)
    assert env["GIF_NEKOSBEST_ATTIVO"] == "no" and env["GIF_PURRBOT_ATTIVO"] == "si" and "ALTRO" not in env
    assert f.env_con_file({}, tmp_path / "manca.env") == {}


def test_categorie_per_adulti_non_passano():
    for cattiva in ("nsfw", "lewd", "hentai", "blowjob", "anime porn", "loli", "ero", "shota"):
        assert not f.categoria_sfw(cattiva), cattiva
    for buona in ("hug", "anime hug", "highfive", "lappillow", "nosebleed"):
        assert f.categoria_sfw(buona), buona
    assert not f.categoria_sfw("")


def test_ogni_categoria_del_catalogo_e_sfw_e_nella_parte_sfw_del_servizio():
    for v in catalogo.tutte():
        assert f.categoria_sfw(v.ricerca), v.id
        for nome, cat in v.fonti.items():
            assert nome in f.FONTI and f.categoria_sfw(cat), (v.id, nome, cat)
            url = f._richiesta(_fonte(nome), v)
            assert url and url.startswith("https://"), (v.id, nome)
            assert "nsfw" not in url
            if nome == "purrbot":
                assert "/img/sfw/" in url
            if nome == "waifupics":
                assert "/sfw/" in url


def test_una_categoria_vietata_o_strana_non_parte():
    v = catalogo.Voce("x", "FUN-0", "azione", {"it": "x"}, (), "anime x", {"waifupics": "nsfw", "purrbot": "../x"})
    assert f._richiesta(_fonte("waifupics"), v) is None
    assert f._richiesta(_fonte("purrbot"), v) is None
    cattiva = catalogo.Voce("y", "FUN-0", "azione", {"it": "y"}, (), "anime hentai", {})
    assert f._richiesta(_fonte("giphy"), cattiva) is None


def test_giphy_chiede_sempre_rating_g():
    url = f._richiesta(_fonte("giphy"), HUG)
    assert "rating=g" in url and "q=anime%20hug" in url and "limit=10" in url


def test_risposte_delle_fonti():
    nb = json.dumps({"results": [{"url": "https://nekos.best/api/v2/hug/1.gif", "anime_name": "Titolo",
                                  "artist_href": "https://x.example/a"}]})
    g = f.leggi_risposta("nekosbest", nb)[0]
    assert (g.fonte, g.dettaglio, g.link) == ("nekos.best", "Titolo", "https://x.example/a")
    assert f.leggi_risposta("purrbot", json.dumps({"link": "https://purrbot.site/img/a.gif"}))[0].fonte == "purrbot.site"
    assert f.leggi_risposta("waifupics", json.dumps({"url": "https://i.waifu.pics/a.gif"}))
    assert f.leggi_risposta("otakugifs", json.dumps({"url": "https://media.otakugifs.xyz/a.gif"}))
    gi = json.dumps({"data": [{"url": "https://giphy.com/gifs/a", "images": {"downsized_medium": {"url": "https://media1.giphy.com/a.gif"}}}]})
    r = f.leggi_risposta("giphy", gi)[0]
    assert r.dettaglio == "Powered by GIPHY" and r.link == "https://giphy.com/gifs/a"


def test_risposte_fuori_dominio_o_non_https_o_rotte_si_scartano():
    assert f.leggi_risposta("waifupics", json.dumps({"url": "https://evil.example/a.gif"})) == []
    assert f.leggi_risposta("waifupics", json.dumps({"url": "http://i.waifu.pics/a.gif"})) == []
    assert f.leggi_risposta("waifupics", json.dumps({"url": "https://waifu.pics.evil.example/a.gif"})) == []
    assert f.leggi_risposta("waifupics", "non json") == []
    assert f.leggi_risposta("nekosbest", json.dumps([1])) == []


class _Rete:
    def __init__(self, risposte):
        self.risposte = risposte  # sottostringa dell'indirizzo -> testo o None
        self.chiamate = []

    async def __call__(self, url):
        self.chiamate.append(url)
        for chiave, testo in self.risposte.items():
            if chiave in url:
                return testo
        return None


def _ok(host, n=1):
    return json.dumps({"url": f"https://{host}/{n}.gif"})


async def test_ripiego_sulla_fonte_che_risponde():
    rete = _Rete({"purrbot": None, "waifu.pics": _ok("i.waifu.pics")})
    s = f.ServizioGif([_fonte("purrbot"), _fonte("waifupics")], rete, random.Random(1))
    g = await s.prendi(HUG)
    assert g.fonte == "waifu.pics"
    assert any("purrbot" in u for u in rete.chiamate)


async def test_giro_tra_le_fonti_accese():
    rete = _Rete({"purrbot": json.dumps({"link": "https://purrbot.site/a.gif"}), "waifu.pics": _ok("i.waifu.pics")})
    s = f.ServizioGif([_fonte("purrbot"), _fonte("waifupics")], rete, random.Random(1))
    viste = {(await s.prendi(HUG)).fonte for _ in range(4)}
    assert viste == {"purrbot.site", "waifu.pics"}


async def test_nessuna_fonte_o_voce_non_coperta_da_none_senza_rete():
    rete = _Rete({})
    assert await f.ServizioGif([], rete).prendi(HUG) is None
    dab = catalogo.trova("reazione", "dab")
    assert await f.ServizioGif([_fonte("purrbot")], rete).prendi(dab) is None
    assert rete.chiamate == []


async def test_cache_con_tetto_e_riposo_della_fonte():
    t = [0.0]
    rete = _Rete({"waifu.pics": _ok("i.waifu.pics")})
    s = f.ServizioGif([_fonte("waifupics")], rete, random.Random(1), adesso=lambda: t[0])
    await s.prendi(HUG)
    await s.prendi(HUG)
    assert len(rete.chiamate) == 2  # poche GIF in cache: si continua a chiedere (stesso indirizzo, stessa GIF)
    # con il tetto di GIF in cache non si chiama più la rete
    s._salva("waifupics", HUG, [f.Gif(f"https://i.waifu.pics/{i}.gif", "waifu.pics") for i in range(30)])
    assert len(s._in_cache("waifupics", HUG)) == f.MAX_GIF_PER_VOCE
    prima = len(rete.chiamate)
    await s.prendi(HUG)
    assert len(rete.chiamate) == prima
    # scaduta la cache, torna la rete; una fonte muta riposa
    t[0] = f.DURATA_CACHE_SECONDI + 1
    muta = _Rete({})
    s2 = f.ServizioGif([_fonte("purrbot")], muta, adesso=lambda: t[0])
    assert await s2.prendi(HUG) is None and await s2.prendi(HUG) is None
    assert len(muta.chiamate) == 1
    t[0] += f.PAUSA_FONTE_SECONDI + 1
    await s2.prendi(HUG)
    assert len(muta.chiamate) == 2


async def test_un_errore_della_fonte_non_rompe_il_giro():
    async def rotta(url):
        raise RuntimeError("boom")

    assert await f.ServizioGif([_fonte("purrbot")], rotta).prendi(HUG) is None
