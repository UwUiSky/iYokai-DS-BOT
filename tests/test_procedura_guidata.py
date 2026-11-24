"""
tests/test_procedura_guidata.py
===============================
UTL-121 (D124): schema delle procedure guidate. Legata all'autore, Annulla non scrive niente,
permessi riletti a ogni passo e alla conferma, doppia conferma scrive una volta sola.
"""

from unittest.mock import AsyncMock

import pytest

from core.procedura_guidata import Fase, Passo, StatoProcedura, VistaGuidata
from tests.support.discord_fakes import fake_interaction, fake_member


def _stato():
    return StatoProcedura(autore_id=7, passi=(Passo("a", ("x",)), Passo("b")))


def test_avanti_chiede_i_dati_poi_arriva_al_riepilogo():
    s = _stato()
    assert s.avanti() == ("x",) and s.indice == 0
    s.dati["x"] = 1
    assert s.avanti() == () and s.indice == 1
    s.avanti()
    assert s.al_riepilogo
    s.indietro()
    assert s.indice == 1


def test_annulla_butta_i_dati_e_non_si_conferma():
    s = _stato()
    s.dati["x"] = 1
    s.avanti(); s.avanti()
    s.annulla()
    assert s.fase is Fase.ANNULLATA and s.dati == {}
    assert s.conferma() is False


def test_conferma_una_volta_sola():
    s = _stato()
    s.dati["x"] = 1
    s.avanti(); s.avanti()
    assert s.conferma() is True
    assert s.conferma() is False


def _vista(stato, permesso=None, conferma=None):
    async def ok(_i):
        return None

    return VistaGuidata(
        stato, titolo="T", lingua="it", permesso=permesso or ok, costruttori={},
        testi={"a": lambda v: "a", "b": lambda v: "b"}, riepilogo=lambda v: "r",
        conferma=conferma or AsyncMock(return_value="fatto"),
    )


def _clic(user_id):
    return fake_interaction(user=fake_member(user_id=user_id))


@pytest.mark.asyncio
async def test_vista_legata_all_autore():
    vista = _vista(_stato())
    assert await vista.autorizza(_clic(8)) is False
    assert await vista.autorizza(_clic(7)) is True


@pytest.mark.asyncio
async def test_permesso_tolto_a_meta_annulla_senza_scrivere():
    perso = {"v": False}

    async def permesso(_i):
        return "no" if perso["v"] else None

    conferma = AsyncMock(return_value="fatto")
    s = _stato()
    s.dati["x"] = 1
    vista = _vista(s, permesso, conferma)
    assert await vista.autorizza(_clic(7)) is True
    perso["v"] = True
    assert await vista.autorizza(_clic(7)) is False
    assert s.fase is Fase.ANNULLATA and s.dati == {}
    conferma.assert_not_awaited()


@pytest.mark.asyncio
async def test_annulla_non_chiama_la_scrittura():
    conferma = AsyncMock(return_value="fatto")
    s = _stato()
    vista = _vista(s, conferma=conferma)
    await vista._annulla(_clic(7))
    conferma.assert_not_awaited()
    assert s.fase is Fase.ANNULLATA


@pytest.mark.asyncio
async def test_doppia_conferma_scrive_una_volta():
    conferma = AsyncMock(return_value="fatto")
    s = _stato()
    s.dati["x"] = 1
    s.avanti(); s.avanti()
    vista = _vista(s, conferma=conferma)
    await vista._conferma_premuto(_clic(7))
    await vista._conferma_premuto(_clic(7))
    assert conferma.await_count == 1
