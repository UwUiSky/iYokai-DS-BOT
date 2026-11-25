"""
tests/test_music_cartella.py
============================
Catalogo MUS (issue #126) giro r7mus: MUS-018, cartella di brani dell'owner (D111).
Scansione sicura, titoli puliti, tabella, comando `/owner radio cartella`, `/music coda anteprime`.
"""

import os
from types import SimpleNamespace

import pytest

from core import music_cartella_logic as cl
from core.repositories.music_cartella_repo import MusicCartellaRepository


def _file(percorso, contenuto=b"x" * 100):
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_bytes(contenuto)
    return percorso


# ----------------------------- titoli -----------------------------
def test_titolo_dal_nome_e_pulito_e_senza_percorsi():
    assert cl.titolo_dal_nome("Mia_canzone-demo.mp3") == "Mia canzone - demo"
    assert cl.titolo_dal_nome("cartella/segreta/brano.flac") == "brano"
    assert cl.titolo_dal_nome("..\\..\\etc\\brano.wav") == "brano"
    assert cl.titolo_dal_nome("@everyone `x` [a](b).mp3") == "everyone 'x' (a)(b)"
    assert cl.titolo_dal_nome(".mp3") == cl.TITOLO_PREDEFINITO
    assert len(cl.titolo_dal_nome("a" * 500 + ".mp3")) <= cl.MAX_TITOLO


def test_titolo_dai_metadati_scarta_percorsi_e_nomi_di_file():
    assert cl.titolo_dai_metadati("Titolo vero", "riserva") == "Titolo vero"
    for male in ("/audio/local/a.mp3", "a.mp3", "C:\\musica\\a", "local:/x", "Unknown title", "", None, 5):
        assert cl.titolo_dai_metadati(male, "riserva") == "riserva"
    assert cl.titolo_dai_metadati("Ciao\n\x00 mondo", "r") == "Ciao mondo"


def test_percorso_per_il_nodo_e_percorso_relativo_valido():
    assert cl.percorso_per_il_nodo("/audio/local/", "a/b.mp3") == "/audio/local/a/b.mp3"
    for bene in ("a.mp3", "a/b.mp3"):
        assert cl.percorso_relativo_valido(bene)
    for male in ("", "/a.mp3", "../a.mp3", "a/../b.mp3", "a//b.mp3", "a\\b", "~/a", "a\x00.mp3", "x" * 501):
        assert not cl.percorso_relativo_valido(male)


def test_cartella_dell_owner_usa_la_radio_se_manca():
    assert cl.cartella_dell_owner("/m", "/r") == "/m"
    assert cl.cartella_dell_owner("", "/r") == "/r"
    assert cl.cartella_dell_owner(" ", "") == ""


# ----------------------------- scansione -----------------------------
def test_scansione_solo_estensioni_ammesse_e_niente_nascosti(tmp_path):
    _file(tmp_path / "uno.mp3")
    _file(tmp_path / "Due.FLAC")
    _file(tmp_path / "note.txt")
    _file(tmp_path / "script.sh")
    _file(tmp_path / ".nascosto.mp3")
    _file(tmp_path / ".cartella" / "x.mp3")
    _file(tmp_path / "sotto" / "tre.ogg")
    esito = cl.scansiona(tmp_path)
    assert sorted(b.percorso for b in esito.brani) == ["Due.FLAC", "sotto/tre.ogg", "uno.mp3"]
    assert not esito.troncata


def test_scansione_link_fuori_cartella_scartato_dentro_ammesso(tmp_path):
    fuori = tmp_path / "fuori"
    radice = tmp_path / "radice"
    _file(fuori / "segreto.mp3")
    _file(radice / "vero.mp3")
    os.symlink(fuori / "segreto.mp3", radice / "link-fuori.mp3")
    os.symlink(fuori, radice / "cartella-fuori")
    os.symlink(radice / "vero.mp3", radice / "link-dentro.mp3")
    esito = cl.scansiona(radice)
    percorsi = sorted(b.percorso for b in esito.brani)
    assert "link-fuori.mp3" not in percorsi
    assert not any(p.startswith("cartella-fuori") for p in percorsi)
    assert "vero.mp3" in percorsi and "link-dentro.mp3" in percorsi
    assert esito.scartati >= 1


def test_scansione_tetti_di_file_e_di_peso(tmp_path, monkeypatch):
    for i in range(5):
        _file(tmp_path / f"b{i}.mp3")
    monkeypatch.setattr(cl, "MAX_FILE", 3)
    esito = cl.scansiona(tmp_path)
    assert len(esito.brani) == 3 and esito.troncata and esito.scartati == 2
    monkeypatch.setattr(cl, "MAX_FILE", 500)
    monkeypatch.setattr(cl, "MAX_BYTE_FILE", 50)
    assert cl.scansiona(tmp_path).brani == []
    monkeypatch.setattr(cl, "MAX_BYTE_FILE", 1000)
    monkeypatch.setattr(cl, "MAX_BYTE_TOTALI", 250)
    assert len(cl.scansiona(tmp_path).brani) == 2


def test_scansione_profondita_limitata_cartella_mancante_e_file_vuoti(tmp_path):
    _file(tmp_path / "a" / "b" / "c" / "d" / "troppo.mp3")
    _file(tmp_path / "a" / "b" / "c" / "ok.mp3")
    _file(tmp_path / "vuoto.mp3", b"")
    assert [b.percorso for b in cl.scansiona(tmp_path).brani] == ["a/b/c/ok.mp3"]
    assert cl.scansiona(tmp_path / "non-esiste") == cl.EsitoScansione([], 0, False)
    assert cl.scansiona(_file(tmp_path / "file.txt")).brani == []


# ----------------------------- tabella -----------------------------
@pytest.fixture
def repo(clean_db):
    return MusicCartellaRepository(lambda: clean_db)


def _brano(percorso, titolo="T", dimensione=10, ns=1):
    return cl.BranoCartella(percorso, titolo, dimensione, ns)


async def test_sincronizza_nuovi_tolti_e_cambiati(repo):
    assert await repo.sincronizza([_brano("a.mp3"), _brano("b.mp3")]) == (2, 0, 0)
    primo = (await repo.elenco())[0]
    await repo.imposta_dettagli(primo.id, "Titolo letto", 1234)
    assert await repo.sincronizza([_brano("a.mp3"), _brano("b.mp3")]) == (0, 0, 0)
    assert (await repo.get(primo.id)).durata_ms == 1234  # invariato: si tengono i dettagli
    assert await repo.sincronizza([_brano("a.mp3", dimensione=99), _brano("c.mp3")]) == (1, 1, 1)
    assert [b.percorso for b in await repo.elenco()] == ["a.mp3", "c.mp3"]
    assert (await repo.get(primo.id)).durata_ms is None  # il file e' cambiato: si riparte
    assert await repo.sincronizza([]) == (0, 2, 0)
    assert await repo.conta() == 0


async def test_cerca_per_titolo_senza_sql_dal_testo(repo):
    await repo.sincronizza([_brano("a.mp3", "Alba rossa"), _brano("b.mp3", "Notte")])
    assert [b.titolo for b in await repo.cerca("ALB")] == ["Alba rossa"]
    assert await repo.cerca("'; DROP TABLE music_cartella_brani; --") == []
    assert await repo.conta() == 2


async def test_impostazioni_globali_dell_owner(repo):
    assert await repo.leggi_impostazione("paese_globale") is None
    await repo.scrivi_impostazione("paese_globale", "TR", 1)
    await repo.scrivi_impostazione("paese_globale", "IT", 1)
    assert await repo.leggi_impostazione("paese_globale") == "IT"
    await repo.scrivi_impostazione("paese_globale", None, 1)
    assert await repo.leggi_impostazione("paese_globale") is None


# ----------------------------- brani pronti per la coda -----------------------------
from core import music_anteprime_logic as al  # noqa: E402
from core.repositories.music_cartella_repo import BranoSalvato  # noqa: E402


def _dati(titolo="a.mp3", sorgente="local"):
    return {
        "encoded": "QAAA", "pluginInfo": {"x": 1}, "userData": {"y": 2},
        "info": {
            "identifier": "/audio/local/segreto/a.mp3", "isSeekable": True, "author": "Io", "length": 123000,
            "isStream": False, "position": 0, "title": titolo, "uri": "/audio/local/segreto/a.mp3",
            "artworkUrl": "https://x/y.png", "isrc": "XX", "sourceName": sorgente,
        },
    }


def test_traccia_pulita_senza_percorso_ne_nome_file():
    salvato = BranoSalvato(7, "segreto/a.mp3", "Titolo da nome", None)
    pronto = al.dati_traccia_pulita(_dati("a.mp3"), salvato)
    assert pronto.titolo == "Titolo da nome" and pronto.durata_ms == 123000
    info = pronto.dati["info"]
    assert info["uri"] is None and info["artworkUrl"] is None and info["identifier"] == "anteprima-7"
    assert info["author"] == al.AUTORE and pronto.dati["pluginInfo"] == {} and pronto.dati["userData"] == {}
    assert "segreto" not in repr({k: v for k, v in pronto.dati.items() if k != "encoded"})
    traccia = al.come_ricerca([pronto], "Anteprime")[0]
    assert traccia.uri is None and traccia.title == "Titolo da nome" and traccia.source == "local"


def test_traccia_pulita_usa_il_titolo_dei_metadati_se_sembra_un_titolo():
    salvato = BranoSalvato(1, "a.mp3", "Da nome", None)
    assert al.dati_traccia_pulita(_dati("Vero titolo"), salvato).titolo == "Vero titolo"
    assert al.dati_traccia_pulita(_dati("/audio/local/a.mp3"), salvato).titolo == "Da nome"


def test_traccia_non_locale_o_storta_rifiutata():
    salvato = BranoSalvato(1, "a.mp3", "T", None)
    assert al.dati_traccia_pulita(_dati(sorgente="http"), salvato) is None
    assert al.dati_traccia_pulita(_dati(sorgente="youtube"), salvato) is None
    for storto in (None, {}, {"info": 5}, {"info": {"sourceName": "local"}}, {"encoded": "x", "info": []}):
        assert al.dati_traccia_pulita(storto, salvato) is None


def test_piu_brani_diventano_una_playlist():
    salvato = BranoSalvato(1, "a.mp3", "T", None)
    pronti = [al.dati_traccia_pulita(_dati(), salvato), al.dati_traccia_pulita(_dati(), BranoSalvato(2, "b.mp3", "U", None))]
    playlist = al.come_ricerca(pronti, "Anteprime")
    assert playlist.name == "Anteprime" and len(playlist) == 2


def test_un_brano_della_cartella_non_si_salva_in_nessuna_playlist():
    """Salvare la coda (playlist, coda salvata, «Oggi») non deve mai scrivere il percorso del server."""
    from core.music_playlist_logic import brani_da_coda, brano_da_traccia

    pulita = al.dati_traccia_pulita(_dati(), BranoSalvato(3, "a.mp3", "T", None))
    traccia = al.come_ricerca([pulita], "Anteprime")[0]
    assert brano_da_traccia(traccia) is None
    normale = SimpleNamespace(encoded="QQ", title="Altro", uri="https://youtu.be/x", length=1000, source="youtube")
    brani, fuori = brani_da_coda(traccia, [normale])
    assert [b.titolo for b in brani] == ["Altro"] and fuori == 0


# ----------------------------- comandi -----------------------------
from unittest.mock import AsyncMock  # noqa: E402

import cogs.music.cartella as cartella_mod  # noqa: E402


def _inter(user_id=1, guild=True):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id), guild=SimpleNamespace(id=5) if guild else None, locale=None,
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _cog(repo, monkeypatch, cartella="", owner=1, radio=""):
    monkeypatch.setattr(cartella_mod, "music_cartella_repo", repo)
    monkeypatch.setattr(
        cartella_mod, "config",
        SimpleNamespace(OWNER_ID=owner, MUSICA_CARTELLA_OWNER=cartella, MAIN_RADIO_LOCAL_FOLDER=radio, LAVALINK_LOCAL_ROOT="/audio/local"),
    )
    return cartella_mod.MusicCartellaCog(SimpleNamespace(get_cog=lambda _n: None))


def _testo(inter):
    chiamata = (inter.followup.send if inter.followup.send.await_count else inter.response.send_message).await_args
    return chiamata.args[0] if chiamata.args else chiamata.kwargs.get("content", "")


async def test_owner_cartella_solo_owner_e_cartella_non_impostata(repo, monkeypatch, tmp_path):
    cog = _cog(repo, monkeypatch, cartella=str(tmp_path))
    estraneo = _inter(2)
    await cog.cartella.callback(cog, estraneo, "aggiorna")
    assert await repo.conta() == 0
    cog = _cog(repo, monkeypatch, cartella="")
    inter = _inter(1)
    await cog.cartella.callback(cog, inter, "aggiorna")
    assert "MUSICA_CARTELLA_OWNER" in _testo(inter)


async def test_owner_cartella_aggiorna_ed_elenca_senza_percorsi(repo, monkeypatch, tmp_path):
    _file(tmp_path / "segreto" / "Mia_canzone.mp3")
    _file(tmp_path / "altra.flac")
    cog = _cog(repo, monkeypatch, cartella=str(tmp_path))
    inter = _inter(1)
    await cog.cartella.callback(cog, inter, "aggiorna")
    assert "2 brani" in _testo(inter) and await repo.conta() == 2
    elenco = _inter(1)
    await cog.cartella.callback(cog, elenco, "elenco")
    testo = _testo(elenco)
    assert "Mia canzone" in testo and "segreto" not in testo and ".mp3" not in testo and str(tmp_path) not in testo


async def test_la_cartella_della_radio_vale_se_manca_quella_dell_owner(repo, monkeypatch, tmp_path):
    _file(tmp_path / "uno.ogg")
    cog = _cog(repo, monkeypatch, cartella="", radio=str(tmp_path))
    assert (await cartella_mod.aggiorna_elenco())[0] == 1
    assert cog is not None


async def test_anteprime_agli_utenti_si_accendono_e_si_spengono(repo, monkeypatch, tmp_path):
    cog = _cog(repo, monkeypatch, cartella=str(tmp_path))
    assert await cartella_mod.anteprime_abilitate(2) is True  # di base accese
    await cog.cartella.callback(cog, _inter(1), "anteprime-no")
    assert await cartella_mod.anteprime_abilitate(2) is False
    assert await cartella_mod.anteprime_abilitate(1) is True  # l'owner puo' sempre
    await cog.cartella.callback(cog, _inter(1), "anteprime-si")
    assert await cartella_mod.anteprime_abilitate(2) is True


async def test_utente_sceglie_solo_id_o_titolo_mai_un_percorso(repo, monkeypatch, tmp_path):
    cog = _cog(repo, monkeypatch, cartella=str(tmp_path))
    await repo.sincronizza([_brano("a/uno.mp3", "Uno"), _brano("b.mp3", "Due")])
    uno = (await repo.cerca("Uno"))[0]
    assert [b.titolo for b in await cog._scelti(str(uno.id))] == ["Uno"]
    assert [b.titolo for b in await cog._scelti("due")] == ["Due"]
    assert [b.titolo for b in await cog._scelti(None)] == ["Due", "Uno"]
    for percorso in ("a/uno.mp3", "local:/audio/local/b.mp3", "../../etc/passwd", "/audio/local/b.mp3", "99999999"):
        assert await cog._scelti(percorso) == []


async def test_autocompletamento_mostra_solo_titoli_e_id(repo, monkeypatch, tmp_path):
    cog = _cog(repo, monkeypatch, cartella=str(tmp_path))
    await repo.sincronizza([_brano("a/uno.mp3", "Uno")])
    scelte = await cog._scelte(_inter(2), "")
    assert [(s.name, s.value.isdigit()) for s in scelte] == [("Uno", True)]
    await cog.cartella.callback(cog, _inter(1), "anteprime-no")
    assert await cog._scelte(_inter(2), "") == []
    assert len(await cog._scelte(_inter(1), "")) == 1
    cog = _cog(repo, monkeypatch, cartella="")
    assert await cog._scelte(_inter(1), "") == []


class _Musica:
    def __init__(self, nodo, nodo_locale):
        self.nodo, self.nodo_locale, self.risposte, self.risultato = nodo, nodo_locale, [], None

    async def controlli_base(self, interaction):
        return True

    async def accoda(self, guild, membro, query, rispondi, *, interaction=None, cerca=None, **_):
        self.risultato = await cerca(self.nodo, self.nodo_locale)
        if not self.risultato[0]:
            await rispondi("Nessun risultato.")


def _con_musica(cog, musica):
    cog.bot = SimpleNamespace(get_cog=lambda nome: musica if nome == "MusicCog" else None)
    return cog


async def test_anteprime_su_nodo_pubblico_senza_nodo_locale_dice_perche(repo, monkeypatch, tmp_path):
    cog = _cog(repo, monkeypatch, cartella=str(tmp_path))
    await repo.sincronizza([_brano("a.mp3", "Uno")])
    musica = _Musica(SimpleNamespace(identifier="pubblico@main"), None)
    inter = _inter(2)
    await _con_musica(cog, musica).anteprime.callback(cog, inter, None)
    assert "nodo Lavalink locale" in _testo(inter) and "Nessun risultato" not in _testo(inter)


async def test_anteprime_spente_per_gli_utenti_non_chiamano_il_nodo(repo, monkeypatch, tmp_path):
    cog = _cog(repo, monkeypatch, cartella=str(tmp_path))
    await repo.sincronizza([_brano("a.mp3", "Uno")])
    await cog.cartella.callback(cog, _inter(1), "anteprime-no")
    musica = _Musica(SimpleNamespace(identifier="iyokai-local-node@main"), None)
    inter = _inter(2)
    await _con_musica(cog, musica).anteprime.callback(cog, inter, None)
    assert musica.risultato is None and "non sono disponibili" in _testo(inter)


async def test_anteprime_legge_dal_nodo_locale_e_passa_brani_puliti(repo, monkeypatch, tmp_path):
    cog = _cog(repo, monkeypatch, cartella=str(tmp_path))
    await repo.sincronizza([_brano("sotto/uno.mp3", "Uno"), _brano("due.mp3", "Due")])
    visti = []

    async def finta_fetch(percorso, node=None):
        visti.append(percorso)
        import wavelink
        return [wavelink.Playable(_dati("x.mp3"))]

    import wavelink
    monkeypatch.setattr(wavelink.Pool, "fetch_tracks", staticmethod(finta_fetch))
    locale = SimpleNamespace(identifier="iyokai-local-node@main")
    musica = _Musica(SimpleNamespace(identifier="pubblico@main"), locale)
    inter = _inter(2)
    await _con_musica(cog, musica).anteprime.callback(cog, inter, None)
    risultati, nodo = musica.risultato
    assert nodo is locale and risultati.name == "Anteprime" and len(risultati) == 2
    assert sorted(visti) == ["/audio/local/due.mp3", "/audio/local/sotto/uno.mp3"]  # percorso del nodo, mai scritto dall'utente
    for traccia in risultati:
        assert traccia.uri is None and "audio" not in traccia.identifier and traccia.source == "local"


async def test_il_testo_di_un_brano_in_anteprima_non_si_cerca_all_esterno(monkeypatch):
    """Il titolo di un brano non ancora pubblicato non va a LRCLIB."""
    from tests.test_music_controllo import _player, _prepara
    import cogs.music.controllo as controllo_module

    brano = SimpleNamespace(title="Inedito", author="Anteprima", length=200_000, is_seekable=True, source="local")
    c, _m, i = _prepara(_player([], corrente=brano), monkeypatch)
    chiamato = AsyncMock()
    monkeypatch.setattr(controllo_module, "cerca_testi", chiamato)
    await c.brano_testo.callback(c, i)
    chiamato.assert_not_awaited()
    assert "anteprima" in i.response.inviati[0]
