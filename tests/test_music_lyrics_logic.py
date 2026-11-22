"""
tests/test_music_lyrics_logic.py
================================
MUS-046: testi da LRCLIB con risposte finte (nessuna rete): pulizia del titolo, lettura LRC, riga del karaoke,
servizio che non risponde, tetto di byte, memoria.
"""

import json

import pytest

from core import music_lyrics_logic as L

LRC = "[ar:Qualcuno]\n[00:10.50]prima\n[00:20.00]seconda\n[00:20.00][01:05.5]ripetuta\n  rotta\n[xx]no\n"


def test_titolo_ripulito():
    assert L.ripulisci_titolo("Queen - Bohemian Rhapsody (Official Video)", "QueenVEVO") == ("Bohemian Rhapsody", "Queen")
    assert L.ripulisci_titolo("Bohemian Rhapsody [Remastered 2011]", "Queen - Topic") == ("Bohemian Rhapsody", "Queen")
    assert L.ripulisci_titolo("Solo titolo", "Autore") == ("Solo titolo", "Autore")


def test_lrc_letto_in_ordine_e_senza_righe_rotte():
    righe = L.leggi_lrc(LRC)
    assert righe[0] == (10_500, "prima")
    assert (20_000, "seconda") in righe and (20_000, "ripetuta") in righe and (65_500, "ripetuta") in righe
    assert [r[0] for r in righe] == sorted(r[0] for r in righe)
    assert len(righe) == 4


def test_lrc_ha_un_tetto_di_righe_e_di_lunghezza():
    enorme = "\n".join(f"[{n // 60:02d}:{n % 60:02d}.00]{'x' * 500}" for n in range(2000))
    righe = L.leggi_lrc(enorme)
    assert len(righe) == L.MAX_RIGHE and all(len(r[1]) <= L.MAX_RIGA for r in righe)


def test_riga_corrente():
    righe = L.leggi_lrc(LRC)
    assert L.indice_riga(righe, 0) == -1
    assert L.indice_riga(righe, 10_500) == 0
    assert L.indice_riga(righe, 25_000) == 2  # a pari tempo vale l'ultima
    assert "**prima**" in L.testo_karaoke(righe, 0) and "seconda" in L.testo_karaoke(righe, 0)
    assert L.testo_karaoke(righe, -1).startswith("♪")
    assert len(L.testo_karaoke(righe, 1, massimo=10)) <= 10


def _voce(**kw):
    base = {"trackName": "Canzone", "artistName": "Artista", "duration": 200.0, "plainLyrics": "ciao\nmondo", "syncedLyrics": LRC}
    base.update(kw)
    return base


class _Rete:
    def __init__(self, get=None, search=None):
        self.get, self.search, self.url = get, search, []

    async def __call__(self, url, *, max_bytes):
        self.url.append((url, max_bytes))
        if url.startswith(L.URL_GET):
            return json.dumps(self.get) if self.get is not None else None
        return json.dumps(self.search) if self.search is not None else None


@pytest.mark.asyncio
async def test_testo_esatto_con_tetto_di_byte():
    L.svuota_memoria()
    rete = _Rete(get=_voce())
    t = await L.cerca_testi("Artista - Canzone (Official Video)", "Boh", 200_000, scarica=rete)
    assert t.sincronizzato == LRC and t.semplice == "ciao\nmondo"
    assert rete.url[0][1] == L.MAX_BYTE_RISPOSTA
    assert "track_name=Canzone" in rete.url[0][0] and "artist_name=Artista" in rete.url[0][0] and "duration=200" in rete.url[0][0]


@pytest.mark.asyncio
async def test_senza_esatto_si_usa_la_ricerca_con_durata_vicina():
    L.svuota_memoria()
    rete = _Rete(search=[_voce(duration=400.0, plainLyrics="sbagliato"), _voce(duration=198.0, plainLyrics="giusto")])
    t = await L.cerca_testi("Canzone", "Artista", 200_000, scarica=rete)
    assert t.semplice == "giusto"


@pytest.mark.asyncio
async def test_nessun_testo_e_strumentale():
    L.svuota_memoria()
    assert await L.cerca_testi("Canzone", "Artista", 200_000, scarica=_Rete(search=[])) is None
    L.svuota_memoria()
    assert await L.cerca_testi("Canzone", "Artista", 200_000, scarica=_Rete(search=[_voce(instrumental=True)])) is None


@pytest.mark.asyncio
async def test_servizio_che_non_risponde_si_dice():
    L.svuota_memoria()
    with pytest.raises(L.ServizioNonRisponde):
        await L.cerca_testi("Canzone", "Artista", 200_000, scarica=_Rete())
    L.svuota_memoria()
    class Rotta(_Rete):
        async def __call__(self, url, *, max_bytes):
            return "<html>errore</html>"
    with pytest.raises(L.ServizioNonRisponde):
        await L.cerca_testi("Canzone", "Artista", 200_000, scarica=Rotta())


@pytest.mark.asyncio
async def test_la_memoria_evita_la_seconda_richiesta():
    L.svuota_memoria()
    rete = _Rete(get=_voce())
    await L.cerca_testi("Canzone", "Artista", 200_000, scarica=rete)
    n = len(rete.url)
    await L.cerca_testi("Canzone", "Artista", 200_000, scarica=rete)
    assert len(rete.url) == n
    L.svuota_memoria()


def test_testo_troncato():
    assert len(L.tronca_testo("a" * 5000)) == L.TESTO_MAX and L.tronca_testo("a" * 5000).endswith("…")
