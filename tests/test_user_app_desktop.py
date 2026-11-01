"""
tests/test_user_app_desktop.py
==============================
SPEC D.1, D.5 (#108): i comandi dell'app che collegano iYokai Desktop. Il token si mostra una volta e non si salva.
"""

import re
from unittest.mock import MagicMock

import pytest

import cogs.user_app.desktop as dc
from core import desktop_logic as dl
from core.repositories.desktop_repo import DesktopRepository
from tests.support.discord_fakes import fake_interaction, fake_member


@pytest.fixture
def cog(monkeypatch, clean_db):
    repo = DesktopRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(dc, "desktop_repo", repo)
    c = dc.DesktopCog(MagicMock())
    c.repo = repo
    return c


def _i(user_id=7):
    return fake_interaction(user=fake_member(user_id=user_id))


def _testo(i):
    return i.response.send_message.await_args.args[0]


async def test_collega_mostra_il_token_in_privato_e_salva_solo_l_impronta(cog, clean_db):
    i = _i()
    await cog.collega.callback(cog, i)
    token = re.search(r"dsk_[A-Za-z0-9_-]{43}", _testo(i)).group(0)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    righe = await clean_db.fetch("SELECT * FROM desktop_tokens")
    assert len(righe) == 1 and righe[0]["token_hash"] == dl.impronta(token) and token not in str(dict(righe[0]))
    assert await cog.repo.utente_del_token(dl.impronta(token)) == 7


async def test_nuovo_codice_sostituisce_il_vecchio_e_scollega_lo_revoca(cog):
    primo, secondo = _i(), _i()
    await cog.collega.callback(cog, primo)
    await cog.collega.callback(cog, secondo)
    vecchio = re.search(r"dsk_\S{43}", _testo(primo)).group(0)
    nuovo = re.search(r"dsk_\S{43}", _testo(secondo)).group(0)
    assert await cog.repo.utente_del_token(dl.impronta(vecchio)) is None
    assert await cog.repo.utente_del_token(dl.impronta(nuovo)) == 7
    i = _i()
    await cog.scollega.callback(cog, i)
    assert "non vale più" in _testo(i)
    i = _i()
    await cog.scollega.callback(cog, i)
    assert "nessun codice" in _testo(i)


async def test_avvisi_e_parole(cog):
    i = _i()
    await cog.avvisi.callback(cog, i, True)
    assert "accesi" in _testo(i) and (await cog.repo.preferenze(7)).menzioni
    i = _i()
    await cog.parole.callback(cog, i, "Torneo, ciao")
    assert "torneo, ciao" in _testo(i) and (await cog.repo.preferenze(7)).parole == ("torneo", "ciao")
    i = _i()
    await cog.parole.callback(cog, i, "x")
    assert "da 2 a 30" in _testo(i)
    i = _i()
    await cog.parole.callback(cog, i, "")
    assert "tolte" in _testo(i) and (await cog.repo.preferenze(7)).parole == ()
    i = _i()
    await cog.avvisi.callback(cog, i, False)
    assert "spenti" in _testo(i) and not (await cog.repo.preferenze(7)).menzioni


async def test_stato(cog):
    i = _i()
    await cog.stato.callback(cog, i)
    assert "non collegato" in _testo(i) and "spenti" in _testo(i)
    await cog.repo.imposta_token(7, "d" * 64)
    await cog.repo.imposta_menzioni(7, True)
    await cog.repo.imposta_parole(7, ["ciao"])
    i = _i()
    await cog.stato.callback(cog, i)
    assert "Programma: collegato" in _testo(i) and "accesi" in _testo(i) and "ciao" in _testo(i)
