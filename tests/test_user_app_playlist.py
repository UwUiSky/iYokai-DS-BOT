"""
tests/test_user_app_playlist.py
===============================
SPEC B.8 (#107): playlist personali e `/radio ora` di iYokai App (logica e comandi).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.user_app.radio as rc
from core import user_app_playlist as up
from core.repositories.main_radio_repo import MainRadioState, MainRadioTrack
from core.repositories.user_app_repo import UserAppRepository
from core.user_app_strumenti import ErroreStrumento
from tests.support.discord_fakes import fake_interaction, fake_member


def test_nome_brano_e_link():
    assert up.nome_playlist(" Mia-1 ") == "mia-1"
    with pytest.raises(ErroreStrumento) as e:
        up.nome_playlist("con spazio")
    assert e.value.chiave == "app_playlist_nome_non_valido"
    assert up.pulisci_brano("  Titolo \n  artista ") == "Titolo artista"
    for brutto in ("", "  ", "x" * 101):
        with pytest.raises(ErroreStrumento):
            up.pulisci_brano(brutto)
    assert up.link_testo("a b&c") == "https://genius.com/search?q=a+b%26c"
    assert up.righe_playlist(["a", "b"]) == "1. a\n2. b"


@pytest.fixture
def cog(monkeypatch, clean_db):
    monkeypatch.setattr(rc, "user_app_repo", UserAppRepository(pool_provider=lambda: clean_db))
    return rc.RadioCog(MagicMock())


def _i(user_id=7):
    return fake_interaction(user=fake_member(user_id=user_id))


def _testo(i):
    return i.response.send_message.await_args.args[0]


async def test_playlist_dal_crea_all_elimina(cog):
    i = _i()
    await cog.crea.callback(cog, i, "Mia")
    assert "creata" in _testo(i)
    i = _i()
    await cog.crea.callback(cog, i, "mia")
    assert "esiste già" in _testo(i)
    i = _i()
    await cog.aggiungi.callback(cog, i, "mia", "Brano  uno")
    assert "aggiunto" in _testo(i)
    i = _i()
    await cog.mostra.callback(cog, i, "mia")
    assert "1. Brano uno" in i.response.send_message.await_args.kwargs["embed"].description
    i = _i()
    await cog.elenco.callback(cog, i)
    assert "`mia` (1)" in i.response.send_message.await_args.kwargs["embed"].description
    i = _i()
    await cog.togli.callback(cog, i, "mia", 1)
    assert "tolto" in _testo(i)
    i = _i()
    await cog.togli.callback(cog, i, "mia", 1)
    assert "Non c'è" in _testo(i)
    i = _i()
    await cog.elimina.callback(cog, i, "mia")
    assert "eliminata" in _testo(i)
    i = _i()
    await cog.mostra.callback(cog, i, "mia")
    assert "Non trovo" in _testo(i)


async def test_nome_non_valido_e_playlist_di_altri(cog):
    i = _i()
    await cog.crea.callback(cog, i, "con spazio")
    assert "1 a 32" in _testo(i)
    await cog.crea.callback(cog, _i(1), "sua")
    i = _i(2)
    await cog.aggiungi.callback(cog, i, "sua", "x")
    assert "Non trovo" in _testo(i)


async def test_autocompletamento_solo_le_mie(cog):
    await cog.crea.callback(cog, _i(1), "rock")
    await cog.crea.callback(cog, _i(2), "rap")
    scelte = await rc._completa(_i(1), "r")
    assert [s.value for s in scelte] == ["rock"]


async def test_radio_ora_spenta_e_in_onda(cog, monkeypatch):
    adesso = datetime.now(timezone.utc)
    traccia = MainRadioTrack(1, 0, "local:/x.mp3", 600_000, "Canzone <uno>", 1, adesso)
    finto = SimpleNamespace(list_tracks=AsyncMock(return_value=[traccia]), get_state=AsyncMock(return_value=None))
    monkeypatch.setattr(rc, "main_radio_repo", finto)
    i = _i()
    await cog.ora.callback(cog, i)
    assert "spenta" in i.followup.send.await_args.args[0]
    finto.get_state.return_value = MainRadioState(0, adesso, True)
    i = _i()
    await cog.ora.callback(cog, i)
    kw = i.followup.send.await_args.kwargs
    assert kw["embed"].title == "Canzone <uno>"
    assert kw["view"].children[0].url.startswith("https://genius.com/search?q=")
