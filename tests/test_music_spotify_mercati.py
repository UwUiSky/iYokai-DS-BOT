"""
tests/test_music_spotify_mercati.py
===================================
Filtro per paese anche per Spotify (MUS-015, D127, D131): senza chiavi o senza paese niente rete e il brano passa; con le
chiavi un'unica richiesta per lotto, `available_markets` nei dati del brano, poi il filtro di sempre; cache; pausa al
429; token da rinnovare al 401; errori = il brano passa. Risposte finte, nessuna rete.
"""

from types import SimpleNamespace

import pytest

from core import music_spotify_mercati as sp
from core.music_paese_logic import non_disponibile, togli_non_disponibili

ID_A, ID_B, ID_C = "4uLU6hMCjMI75M1A2tKUQC", "7ouMYWpwJ422jRcDASZB7P", "1301WleyT98MSxVHPZCA6M"


def brano(id_=ID_A, uri=None, plugin=None):
    return SimpleNamespace(
        uri=uri if uri is not None else f"https://open.spotify.com/track/{id_}",
        raw_data={"info": {}, "pluginInfo": plugin if plugin is not None else {}}, title="t",
    )


class Finta:
    def __init__(self):
        self.chiamate = []
        self.mercati = {ID_A: ["IT", "US"], ID_B: ["US"], ID_C: []}
        self.stato_brani = 200
        self.stato_token = 200
        self.attesa = 0.0

    async def __call__(self, metodo, url, **kw):
        self.chiamate.append((metodo, url, kw))
        if url == sp.URL_TOKEN:
            return self.stato_token, ({"access_token": "tok", "expires_in": 3600} if self.stato_token == 200 else None), 0.0
        ids = kw["params"]["ids"].split(",")
        corpo = {"tracks": [{"id": i, "available_markets": self.mercati[i]} if i in self.mercati else None for i in ids]}
        return self.stato_brani, (corpo if self.stato_brani == 200 else None), self.attesa


@pytest.fixture
def rete(monkeypatch):
    f = Finta()
    monkeypatch.setattr(sp, "_http", f)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id-finto")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "segreto-finto")
    monkeypatch.setattr(sp, "_cache", sp.OrderedDict())
    monkeypatch.setattr(sp, "_token", {"valore": None, "scade": 0.0})
    monkeypatch.setattr(sp, "_pausa_fino", 0.0)
    monkeypatch.setattr(sp, "_giorno", {"data": "", "richieste": 0})
    return f


@pytest.mark.asyncio
async def test_senza_paese_o_senza_chiavi_nessuna_rete(rete, monkeypatch):
    t = brano()
    assert await sp.arricchisci([t], None) == 0 and rete.chiamate == []
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET")
    assert await sp.arricchisci([t], "FR") == 0 and rete.chiamate == [] and not non_disponibile(t, "FR")


@pytest.mark.asyncio
async def test_brani_scartati_nel_paese_giusto_con_una_sola_richiesta(rete):
    tracce = [brano(ID_A), brano(ID_B), brano(ID_C)]
    assert await sp.arricchisci(tracce, "IT") == 2
    metodi = [c[0] for c in rete.chiamate]
    assert metodi == ["POST", "GET"]  # un solo token e una sola richiesta per tre brani
    assert rete.chiamate[1][2]["headers"]["Authorization"] == "Bearer tok" and "market" not in rete.chiamate[1][2]["params"]
    ammessi, scartati = togli_non_disponibili(tracce, "IT")
    assert [t.uri.rsplit("/", 1)[1] for t in ammessi] == [ID_A, ID_C] and scartati == 1  # C: Spotify non dice i paesi, passa
    assert tracce[0].raw_data["pluginInfo"]["available_markets"] == ["IT", "US"]


@pytest.mark.asyncio
async def test_cache_e_token_riusati_e_brani_non_spotify_ignorati(rete):
    await sp.arricchisci([brano(ID_B)], "IT")
    n = len(rete.chiamate)
    nuova = brano(ID_B)
    assert await sp.arricchisci([nuova, brano(uri="https://www.youtube.com/watch?v=abc"), brano(uri="https://open.spotify.com/album/" + ID_A)], "IT") == 1
    assert len(rete.chiamate) == n  # dalla cache
    await sp.arricchisci([brano(ID_A)], "IT")
    assert [c[0] for c in rete.chiamate[n:]] == ["GET"]  # il token vale ancora


@pytest.mark.asyncio
async def test_brano_che_dichiara_gia_i_paesi_non_si_cerca(rete):
    t = brano(plugin={"availableMarkets": ["DE"]})
    assert await sp.arricchisci([t], "IT") == 0 and rete.chiamate == [] and non_disponibile(t, "IT")


@pytest.mark.asyncio
async def test_429_mette_in_pausa_e_il_brano_passa(rete):
    rete.stato_brani, rete.attesa = 429, 45.0
    t = brano(ID_A)
    assert await sp.arricchisci([t], "FR") == 0 and not non_disponibile(t, "FR")
    n = len(rete.chiamate)
    await sp.arricchisci([brano(ID_B)], "FR")
    assert len(rete.chiamate) == n  # in pausa: nessuna richiesta


@pytest.mark.asyncio
async def test_401_azzera_il_token_e_errori_non_bloccano(rete):
    rete.stato_brani = 401
    assert await sp.arricchisci([brano(ID_A)], "FR") == 0 and sp._token["valore"] is None
    rete.stato_brani = 500
    assert await sp.arricchisci([brano(ID_B)], "FR") == 0
    rete.stato_token = 400
    sp._token.update(valore=None, scade=0.0)
    assert await sp.arricchisci([brano(ID_B)], "FR") == 0


@pytest.mark.asyncio
async def test_eccezione_inattesa_non_esce(rete, monkeypatch):
    async def guasto(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(sp, "_http", guasto)
    t = brano()
    assert await sp.arricchisci([t], "FR") == 0 and not non_disponibile(t, "FR")


@pytest.mark.asyncio
async def test_tetti_per_richiesta_e_al_giorno(rete, monkeypatch):
    ids = [f"{i:022d}" for i in range(130)]
    rete.mercati = {i: ["IT"] for i in ids}
    await sp.paesi_dei_brani(ids)
    assert sum(1 for c in rete.chiamate if c[0] == "GET") == sp.MAX_RICHIESTE_PER_COMANDO  # 100 brani su 130
    monkeypatch.setattr(sp, "_giorno", {"data": __import__("time").strftime("%Y-%m-%d", __import__("time").gmtime()), "richieste": sp.MAX_RICHIESTE_AL_GIORNO})
    n = len(rete.chiamate)
    await sp.paesi_dei_brani([f"{i:022d}" for i in range(200, 210)])
    assert len(rete.chiamate) == n


def test_id_del_brano_solo_da_indirizzi_spotify_validi():
    assert sp.id_brano(brano(ID_A)) == ID_A
    assert sp.id_brano(SimpleNamespace(uri=f"spotify:track:{ID_A}")) == ID_A
    assert sp.id_brano(SimpleNamespace(uri=f"https://open.spotify.com.evil.it/track/{ID_A}")) is None
    assert sp.id_brano(SimpleNamespace(uri=f"https://open.spotify.com/track/{ID_A}/../x")) is None
    assert sp.id_brano(SimpleNamespace(uri=None)) is None


@pytest.mark.asyncio
async def test_il_comando_play_scarta_il_brano_spotify_non_ascoltabile_nel_paese(rete, monkeypatch):
    """Dal comando: i paesi arrivano dalla Web API (finta) e il filtro di sempre fa il resto."""
    from tests.test_music_paese import _con_paese, _play, _scena

    _con_paese(monkeypatch, "IT")
    cog, canale, nodo = _scena()
    rete.mercati = {ID_A: ["US"], ID_B: ["IT", "US"]}
    bloccato, libero = brano(ID_A), brano(ID_B)
    bloccato.title, libero.title = "Bloccato", "Libero"
    bloccato.length = libero.length = 1000
    bloccato.extras = libero.extras = None
    i, _ = await _play(cog, nodo, [bloccato, libero])
    messaggio = " ".join(str(m) for m in i.followup.inviati)
    assert "Libero" in messaggio and "Bloccato" not in messaggio
