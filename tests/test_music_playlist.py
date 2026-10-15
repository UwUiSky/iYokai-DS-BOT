"""
tests/test_music_playlist.py
============================
NF-19 (#90) e MUS-082: playlist salvate. Logica pura, repository su
PostgreSQL vero, comandi con un player finto e un nodo finto.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import wavelink

import cogs.music.playlist as modulo
from cogs.music.playlist import MusicPlaylistCog, decodifica_brani
from core.music_playlist_logic import (
    FORMATO_FILE,
    MAX_BRANI_PER_PLAYLIST,
    MAX_PLAYLIST_PER_UTENTE,
    BranoSalvato,
    brani_da_coda,
    brani_da_json,
    file_esportazione,
    leggi_file_importazione,
    nome_valido,
)
from core.repositories.music_playlist_repo import (
    LimitePlaylistRaggiunto,
    MusicPlaylistRepository,
)


def _traccia(i: int, encoded: str | None = None):
    return SimpleNamespace(
        title=f"Brano {i}", uri=f"https://x/{i}", length=1000 * i, encoded=encoded or f"QAAA{i}"
    )


def _payload_traccia(i: int) -> dict:
    return {
        "encoded": f"QAAA{i}",
        "info": {
            "identifier": f"id{i}", "isSeekable": True, "author": "a", "length": 1000,
            "isStream": False, "position": 0, "title": f"Brano {i}", "uri": None,
            "artworkUrl": None, "isrc": None, "sourceName": "http",
        },
        "pluginInfo": {},
        "userData": {},
    }


# ----------------------------------------------------------------- logica
def test_nome_valido():
    assert nome_valido("  Serata   rock ") == "Serata rock"
    assert nome_valido("") is None
    assert nome_valido("x" * 51) is None
    assert nome_valido("a/b") is None
    assert nome_valido("<@123>") is None


def test_brani_da_coda_include_il_brano_in_corso_e_taglia_al_massimo():
    coda = [_traccia(i) for i in range(2, MAX_BRANI_PER_PLAYLIST + 10)]
    brani, fuori = brani_da_coda(_traccia(1), coda)
    assert len(brani) == MAX_BRANI_PER_PLAYLIST
    assert brani[0].titolo == "Brano 1"
    assert fuori == 9


def test_brani_senza_encoded_si_saltano():
    rotta = SimpleNamespace(title="x", uri=None, length=1, encoded=None)
    brani, _ = brani_da_coda(None, [rotta, _traccia(2)])
    assert [b.titolo for b in brani] == ["Brano 2"]


def test_esporta_e_importa_danno_gli_stessi_brani():
    brani = [BranoSalvato("A", "https://a", 1000, "QAAA1"), BranoSalvato("B", None, 2000, "QAAA2")]
    letti, errore = leggi_file_importazione(file_esportazione("Mia", brani))
    assert errore is None
    assert letti == brani


@pytest.mark.parametrize(
    "contenuto,parola",
    [
        (b"non json", "JSON"),
        (json.dumps({"formato": "altro", "brani": []}).encode(), "iYokai"),
        (json.dumps({"formato": FORMATO_FILE, "brani": [{"title": "x"}]}).encode(), "brani validi"),
        (b" " * (256 * 1024 + 1), "KB"),
    ],
)
def test_file_di_importazione_rifiutati(contenuto, parola):
    brani, errore = leggi_file_importazione(contenuto)
    assert brani == [] and parola in errore


def test_brani_da_json_ignora_voci_rotte():
    dati = [{"encoded": "QAAA1", "length": "abc"}, "x", {"encoded": ""}, {"encoded": "QAAA2", "length": 5}]
    brani = brani_da_json(json.dumps(dati))
    assert [(b.encoded, b.durata_ms) for b in brani] == [("QAAA1", 0), ("QAAA2", 5)]


# ----------------------------------------------------------------- repository
@pytest.fixture
def repo(clean_db):
    return MusicPlaylistRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_salva_legge_elenca_cancella(repo):
    brani = [BranoSalvato("A", "https://a", 60000, "QAAA1"), BranoSalvato("B", None, 120000, "QAAA2")]
    assert await repo.save(1, "Rock", brani) is True
    assert await repo.save(1, "Rock", brani[:1]) is False  # sovrascrive
    assert await repo.get(1, "Rock") == brani[:1]
    assert await repo.get(2, "Rock") is None  # di un altro utente

    await repo.save(1, "Altro", brani)
    elenco = await repo.list_for_user(1)
    assert [(r.nome, r.numero_brani, r.durata_ms) for r in elenco] == [
        ("Altro", 2, 180000),
        ("Rock", 1, 60000),
    ]
    assert await repo.delete(1, "Rock") is True
    assert await repo.delete(1, "Rock") is False


@pytest.mark.asyncio
async def test_tetto_di_playlist_per_utente(repo):
    brani = [BranoSalvato("A", None, 1, "QAAA1")]
    for i in range(MAX_PLAYLIST_PER_UTENTE):
        await repo.save(7, f"p{i}", brani)
    with pytest.raises(LimitePlaylistRaggiunto):
        await repo.save(7, "una di troppo", brani)
    assert await repo.save(7, "p0", brani) is False  # sovrascrivere resta permesso


# ----------------------------------------------------------------- comandi
class _Risposte:
    def __init__(self) -> None:
        self.testi: list[str] = []
        self.file = None

    async def send_message(self, testo=None, **kw):
        self.testi.append(testo)
        self.file = kw.get("file")

    async def defer(self, **kw):
        pass

    def is_done(self):
        return False


def _interazione(user_id=1):
    risposte = _Risposte()

    async def _segui(testo=None, **kw):
        risposte.testi.append(testo)

    return SimpleNamespace(
        guild=SimpleNamespace(id=10),
        user=SimpleNamespace(id=user_id, voice=SimpleNamespace(channel=SimpleNamespace(id=3))),
        response=risposte,
        followup=SimpleNamespace(send=_segui),
    ), risposte


class _Musica:
    def __init__(self, player=None) -> None:
        self.player = player
        self.accodate = []

    async def _giocatore_attivo(self, interaction):
        return self.player

    async def _controlli_base(self, interaction):
        return True

    async def accoda(self, guild, membro, query, rispondi, **kw):
        risultati, nodo = await kw["cerca"]("nodo-del-worker", None)
        self.accodate.append((query, risultati, nodo))
        return 3


def _cog(musica, repo, monkeypatch):
    monkeypatch.setattr(modulo, "music_playlist_repo", repo)
    bot = SimpleNamespace(get_cog=lambda nome: musica if nome == "MusicCog" else None)
    return MusicPlaylistCog(bot)


@pytest.mark.asyncio
async def test_salva_la_coda_del_canale(repo, monkeypatch):
    player = SimpleNamespace(current=_traccia(1), queue=[_traccia(2), _traccia(3)])
    cog = _cog(_Musica(player), repo, monkeypatch)
    interazione, risposte = _interazione()

    await cog.salva.callback(cog, interazione, nome="Festa")

    assert "3 brani" in risposte.testi[-1]
    assert [b.encoded for b in await repo.get(1, "Festa")] == ["QAAA1", "QAAA2", "QAAA3"]


@pytest.mark.asyncio
async def test_salva_con_coda_vuota_non_scrive(repo, monkeypatch):
    player = SimpleNamespace(current=None, queue=[])
    cog = _cog(_Musica(player), repo, monkeypatch)
    interazione, risposte = _interazione()
    await cog.salva.callback(cog, interazione, nome="Vuota")
    assert "vuota" in risposte.testi[-1]
    assert await repo.get(1, "Vuota") is None


@pytest.mark.asyncio
async def test_carica_decodifica_sul_nodo_del_worker(repo, monkeypatch):
    await repo.save(1, "Festa", [BranoSalvato("Brano 1", None, 1000, "QAAA1")])
    musica = _Musica()
    cog = _cog(musica, repo, monkeypatch)
    chiamate = []

    async def _decodifica(nodo, nome, brani):
        chiamate.append((nodo, nome, [b.encoded for b in brani]))
        return "playlist-decodificata"

    monkeypatch.setattr(modulo, "decodifica_brani", _decodifica)
    interazione, _ = _interazione()

    await cog.carica.callback(cog, interazione, nome="Festa")

    assert chiamate == [("nodo-del-worker", "Festa", ["QAAA1"])]
    assert musica.accodate == [("Festa", "playlist-decodificata", "nodo-del-worker")]


@pytest.mark.asyncio
async def test_decodifica_brani_fa_una_playlist_wavelink():
    class _Nodo:
        identifier = "n"

        async def send(self, metodo, *, path, data=None):
            assert (metodo, path, data) == ("POST", "v4/decodetracks", ["QAAA1", "QAAA2"])
            return [_payload_traccia(1), _payload_traccia(2)]

    brani = [BranoSalvato("Brano 1", None, 1, "QAAA1"), BranoSalvato("Brano 2", None, 1, "QAAA2")]
    playlist = await decodifica_brani(_Nodo(), "Festa", brani)
    assert isinstance(playlist, wavelink.Playlist)
    assert playlist.name == "Festa" and [t.title for t in playlist] == ["Brano 1", "Brano 2"]


@pytest.mark.asyncio
async def test_esporta_e_importa_dai_comandi(repo, monkeypatch):
    await repo.save(1, "Festa", [BranoSalvato("Brano 1", None, 1000, "QAAA1")])
    cog = _cog(_Musica(), repo, monkeypatch)
    interazione, risposte = _interazione()

    await cog.esporta.callback(cog, interazione, nome="Festa")
    contenuto = risposte.file.fp.read()
    assert json.loads(contenuto)["formato"] == FORMATO_FILE

    async def _leggi():
        return contenuto

    allegato = SimpleNamespace(size=len(contenuto), read=_leggi)
    interazione2, risposte2 = _interazione(user_id=2)
    await cog.importa.callback(cog, interazione2, file=allegato, nome="Copia")
    assert "importata" in risposte2.testi[-1]
    assert [b.encoded for b in await repo.get(2, "Copia")] == ["QAAA1"]
