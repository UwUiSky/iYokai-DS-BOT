"""
tests/test_music_capitoli_fonti.py
==================================
MUS-017: da dove viene l'elenco dei brani (capitoli di Lavalink, descrizione di YouTube) e come si chiede.
"""

import json
from types import SimpleNamespace

import pytest

from core import music_capitoli_fonti as cf

ORA = 3600_000


@pytest.fixture(autouse=True)
def _pulito():
    cf._cache.clear()
    cf._conteggio.update(giorno="", n=0)
    yield


def _traccia(lunghezza=2 * ORA, sorgente="youtube", ident="dQw4w9WgXcQ", stream=False, plugin=None):
    return SimpleNamespace(
        source=sorgente, identifier=ident, length=lunghezza, is_stream=stream,
        raw_data={"pluginInfo": plugin or {}, "info": {}},
    )


def test_candidato_solo_video_youtube_lunghi_ma_non_oltre_8_ore():
    assert cf.candidato(_traccia())
    assert not cf.candidato(_traccia(lunghezza=9 * 60_000))
    assert not cf.candidato(_traccia(lunghezza=8 * ORA + 1))
    assert not cf.candidato(_traccia(sorgente="soundcloud")) and not cf.candidato(_traccia(stream=True))
    for male in ("", "corto", "dQw4w9WgXc/", "../../etc/passwd", "dQw4w9WgXcQ&x=1"):
        assert cf.id_video(_traccia(ident=male)) is None


def test_descrizione_dalla_risposta():
    ok = json.dumps({"items": [{"snippet": {"description": "0:00 A"}}]})
    assert cf.descrizione_da_risposta(ok) == "0:00 A"
    for male in ("", "non json", "{}", '{"items": []}', '{"items": [{"snippet": {"description": 5}}]}', "null", "[]"):
        assert cf.descrizione_da_risposta(male) is None


async def test_la_chiave_va_nell_intestazione_mai_nell_indirizzo(monkeypatch):
    visti = {}

    async def finta(url, *, metodo="GET", headers=None, json_corpo=None, max_bytes=0):
        visti.update(url=url, headers=headers, max_bytes=max_bytes)
        return json.dumps({"items": [{"snippet": {"description": "testo"}}]})

    monkeypatch.setattr(cf, "safe_richiesta", finta)
    assert await cf.descrizione_video("dQw4w9WgXcQ", "SEGRETA") == "testo"
    assert "SEGRETA" not in visti["url"] and visti["headers"] == {"x-goog-api-key": "SEGRETA"}
    assert visti["url"].startswith("https://www.googleapis.com/youtube/v3/videos?")


async def test_senza_chiave_o_con_id_storto_nessuna_richiesta(monkeypatch):
    chiamate = []

    async def finta(*a, **k):
        chiamate.append(1)

    monkeypatch.setattr(cf, "safe_richiesta", finta)
    assert await cf.descrizione_video("dQw4w9WgXcQ", "") is None
    assert await cf.descrizione_video("../x", "chiave") is None
    assert chiamate == []


async def test_cache_e_tetto_giornaliero(monkeypatch):
    chiamate = []

    async def finta(url, **k):
        chiamate.append(url)
        return json.dumps({"items": [{"snippet": {"description": "d"}}]})

    monkeypatch.setattr(cf, "safe_richiesta", finta)
    await cf.descrizione_video("dQw4w9WgXcQ", "k")
    await cf.descrizione_video("dQw4w9WgXcQ", "k")
    assert len(chiamate) == 1  # la seconda e' dalla memoria
    monkeypatch.setattr(cf, "TETTO_GIORNALIERO", 2)
    await cf.descrizione_video("aaaaaaaaaaa", "k")
    assert await cf.descrizione_video("bbbbbbbbbbb", "k") is None and len(chiamate) == 2


async def test_errore_di_rete_non_rompe_e_si_ricorda(monkeypatch):
    async def giu(*a, **k):
        return None

    monkeypatch.setattr(cf, "safe_richiesta", giu)
    assert await cf.descrizione_video("dQw4w9WgXcQ", "k") is None


async def test_prima_i_capitoli_di_lavalink_poi_la_descrizione(monkeypatch):
    descrizione = "0:00 A\n10:00 B\n20:00 C\n"

    async def finta(*a, **k):
        return json.dumps({"items": [{"snippet": {"description": descrizione}}]})

    monkeypatch.setattr(cf, "safe_richiesta", finta)
    voci = await cf.voci_del_video(_traccia(), "k")
    assert [v.titolo for v in voci] == ["A", "B", "C"]
    capitoli = [{"title": "X", "start": 0}, {"title": "Y", "start": 600_000}, {"title": "Z", "start": 1_200_000}]
    voci = await cf.voci_del_video(_traccia(plugin={"chapters": capitoli}), "")  # senza chiave bastano i capitoli
    assert [v.titolo for v in voci] == ["X", "Y", "Z"]
    assert await cf.voci_del_video(_traccia(), "") == []  # niente capitoli e niente chiave
    assert await cf.voci_del_video(_traccia(sorgente="http"), "k") == []
