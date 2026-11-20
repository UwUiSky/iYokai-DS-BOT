"""
tests/test_music_r5_generi.py
=============================
Catalogo MUS (issue #126) giro r5mus: MUS-014, playlist per genere scelte dall'owner.
Logica pura, tabella (tetti), comando `/owner radio genere` e menu `/music genere`.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from core import music_generi_logic as gl
from core.repositories.music_generi_repo import MusicGeneriRepository

PL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
YT = "https://www.youtube.com/playlist?list=PLabcdefghij"


def test_genere_e_titolo_validi():
    assert gl.genere_valido("  Rock   & Roll ") == "Rock & Roll"
    assert gl.titolo_valido("Top 50 (Italia)") == "Top 50 (Italia)"
    for male in ("", "a", "x" * 31, "<@1>", "a\nb", "a/b"):
        assert gl.genere_valido(male) is None
    for male in ("", "x" * 81, "@everyone", "<#1>"):
        assert gl.titolo_valido(male) is None


def test_link_solo_https_di_playlist_o_album_di_una_fonte_nota():
    assert gl.link_valido(PL) == PL and gl.link_valido(YT) == YT
    for male in (
        "http://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",   # non https
        "https://open.spotify.com/track/37i9dQZF1DXcBWIGoYBM5M",     # un brano
        "https://example.com/playlist/1", "javascript:alert(1)", "", "https://127.0.0.1/a",
        PL + "a" * 300,
    ):
        assert gl.link_valido(male) is None, male


def test_raggruppa_ordina_e_non_supera_25_generi():
    voci = [gl.VoceGenere("Rock", "b", PL), gl.VoceGenere("rock", "a", YT), gl.VoceGenere("Jazz", "j", PL)]
    g = gl.raggruppa(voci)
    assert [k.lower() for k in g] == ["jazz", "rock"] and [v.titolo for v in list(g.values())[1]] == ["a", "b"]
    tanti = [gl.VoceGenere(f"Genere {i:02d}", "t", PL) for i in range(40)]
    assert len(gl.raggruppa(tanti)) == gl.MAX_GENERI


# ----------------------------- tabella -----------------------------
@pytest.fixture
def repo(clean_db):
    return MusicGeneriRepository(lambda: clean_db)


async def test_aggiungi_elenca_e_togli(repo):
    assert await repo.aggiungi("Rock", "Classici", PL, 1) == "ok"
    assert await repo.aggiungi("rock", "classici", YT, 1) == "gia"      # stesso titolo
    assert await repo.aggiungi("ROCK", "Altro", PL, 1) == "gia"         # stesso link
    assert await repo.aggiungi("Rock", "Altro", YT, 1) == "ok"
    assert [(v.genere, v.titolo) for v in await repo.elenco()] == [("Rock", "Altro"), ("Rock", "Classici")]
    assert await repo.togli("rock", "ALTRO") == 1
    assert await repo.togli("rock", None) == 1
    assert await repo.elenco() == []
    assert await repo.togli("rock", None) == 0


async def test_tetti_per_genere_e_per_numero_di_generi(repo):
    for i in range(gl.MAX_PLAYLIST_PER_GENERE):
        assert await repo.aggiungi("Rock", f"t{i}", f"{PL}?x={i}", 1) == "ok"
    assert await repo.aggiungi("Rock", "uno-di-troppo", f"{PL}?x=99", 1) == "pieno_genere"
    for i in range(gl.MAX_GENERI - 1):
        assert await repo.aggiungi(f"Genere {i:02d}", "t", f"{YT}&x={i}", 1) == "ok"
    assert await repo.aggiungi("Nuovo genere", "t", f"{YT}&x=zz", 1) == "pieno_generi"
    assert await repo.aggiungi("Rock", "ancora", f"{YT}&x=zz", 1) == "pieno_genere"


async def test_tetto_totale(repo, monkeypatch):
    import core.repositories.music_generi_repo as modulo

    monkeypatch.setattr(modulo, "MAX_TOTALE", 2)
    assert await repo.aggiungi("A1", "t", PL, 1) == "ok"
    assert await repo.aggiungi("A2", "t", YT, 1) == "ok"
    assert await repo.aggiungi("A3", "t", PL + "?a=1", 1) == "pieno_totale"


# ----------------------------- menu e comandi -----------------------------
from core.music_mondo_view import GenereView  # noqa: E402


def _inter(user_id=5, valore="0"):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id), data={"values": [valore]},
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock(), edit_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _gruppi():
    return gl.raggruppa([gl.VoceGenere("Rock", "Classici", PL), gl.VoceGenere("Jazz", "Notte", YT)])


async def test_menu_prima_i_generi_poi_le_playlist_e_avvia_il_link():
    avvia = AsyncMock()
    vista = GenereView(5, _gruppi(), "it", avvia)
    menu = vista.children[0]
    assert [o.label for o in menu.options] == ["Jazz", "Rock"]
    inter = _inter(valore="1")
    await vista._scelto_genere(inter)
    assert vista.genere == "Rock" and [o.label for o in vista.children[0].options] == ["Classici"]
    inter.response.edit_message.assert_awaited_once()
    await vista._scelta_playlist(_inter(valore="0"))
    assert avvia.await_args.args[1].link == PL


async def test_menu_valori_strani_e_utenti_estranei():
    avvia = AsyncMock()
    vista = GenereView(5, _gruppi(), "it", avvia)
    brutta = _inter(valore="99")
    await vista._scelto_genere(brutta)
    assert vista.genere is None
    await vista._scelta_playlist(_inter(valore="0"))  # nessun genere scelto
    avvia.assert_not_awaited()
    estraneo = _inter(user_id=9)
    assert await vista.interaction_check(estraneo) is False


async def test_menu_con_molti_generi_resta_a_25():
    tanti = gl.raggruppa([gl.VoceGenere(f"Genere {i:02d}", "t", PL) for i in range(40)])
    assert len(GenereView(5, tanti, "it", AsyncMock()).children[0].options) == 25


def _owner_cog():
    from cogs.music.owner import MusicOwnerCog

    return MusicOwnerCog(SimpleNamespace())


def _inter_owner(user_id):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id), guild=None, locale=None,
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


async def test_owner_genere_solo_per_l_owner(repo, monkeypatch):
    import cogs.music.owner as modulo

    monkeypatch.setattr(modulo, "music_generi_repo", repo)

    cog = _owner_cog()
    monkeypatch.setattr(modulo, "config", SimpleNamespace(OWNER_ID=1, LAVALINK_PASSWORD="", LAVALINK_LOG_FILE=""))
    inter = _inter_owner(2)
    await cog.genere.callback(cog, inter, "aggiungi", "Rock", "Classici", PL)
    assert await modulo.music_generi_repo.elenco() == []
    inter.response.send_message.assert_awaited_once()


async def test_owner_genere_aggiungi_rifiuta_link_non_sicuri_e_scrive_quelli_buoni(repo, monkeypatch):
    import cogs.music.owner as modulo

    monkeypatch.setattr(modulo, "music_generi_repo", repo)

    cog = _owner_cog()
    monkeypatch.setattr(modulo, "config", SimpleNamespace(OWNER_ID=1, LAVALINK_PASSWORD="", LAVALINK_LOG_FILE=""))
    ok = {"v": False}

    async def sicuro(url):
        return ok["v"]

    monkeypatch.setattr(modulo, "url_e_sicuro", sicuro)
    await cog.genere.callback(cog, _inter_owner(1), "aggiungi", "Rock", "Classici", PL)
    assert await modulo.music_generi_repo.elenco() == []   # indirizzo non pubblico: niente
    ok["v"] = True
    await cog.genere.callback(cog, _inter_owner(1), "aggiungi", "Rock", "Classici", "http://x.example.com/playlist/1")
    assert await modulo.music_generi_repo.elenco() == []   # link non valido
    await cog.genere.callback(cog, _inter_owner(1), "aggiungi", "Rock", "Classici", PL)
    assert [v.titolo for v in await modulo.music_generi_repo.elenco()] == ["Classici"]
    await cog.genere.callback(cog, _inter_owner(1), "togli", "Rock", "", "")
    assert await modulo.music_generi_repo.elenco() == []
