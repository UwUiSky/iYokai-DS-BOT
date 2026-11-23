"""
tests/test_sondaggio_premio_eco051.py
=====================================
ECO-051 (D121): un sondaggio con premio in monete, estratto a sorte tra chi ha votato (mai i bot), una volta sola.
Database vero, sondaggio finto.
"""

import random
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import sondaggio_premio as sp
from core.repositories.leveling_repo import leveling_repo
from core.repositories.sondaggi_nativi_repo import sondaggi_nativi_repo

G, C = 1010001, 77


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    yield


def _utente(i, bot=False):
    u = MagicMock()
    u.id, u.bot, u.mention = i, bot, f"<@{i}>"
    return u


def _messaggio(votanti):
    class _Voti:
        def __init__(self, gente):
            self.gente = gente

        def voters(self):
            async def gen():
                for u in self.gente:
                    yield u

            return gen()

    msg = MagicMock()
    msg.poll.answers = [_Voti(votanti[:2]), _Voti(votanti[1:])]  # la persona 2 ha votato due opzioni
    msg.channel.send = AsyncMock()
    return msg


def test_scelta_dei_vincitori_senza_doppioni_e_con_tetto():
    gente = [_utente(i) for i in range(1, 8)]
    assert len(sp.scegli(gente, 3, random.Random(1))) == 3
    assert len({u.id for u in sp.scegli(gente, 3, random.Random(1))}) == 3
    assert len(sp.scegli(gente[:2], 5, random.Random(1))) == 2  # meno votanti dei premi
    assert sp.scegli([], 3, random.Random(1)) == []


async def test_il_premio_va_ai_votanti_veri_una_volta_sola(clean_db):
    nid = await sondaggi_nativi_repo.crea(G, C, 5, "Domanda?", ["a", "b"], stato="aperto", premio=500, vincitori=2)
    votanti = [_utente(1), _utente(2), _utente(3, bot=True), _utente(4)]
    r = await sondaggi_nativi_repo.prendi(nid)
    msg = _messaggio(votanti)
    vincitori = await sp.premia(G, r, msg, random.Random(3))
    assert len(vincitori) == 2 and all(not u.bot for u in vincitori)
    for u in vincitori:
        assert (await leveling_repo.get_totals(G, u.id)).coins_total == 500
    msg.channel.send.assert_awaited_once()
    assert msg.channel.send.await_args.kwargs["allowed_mentions"].everyone is False
    assert await sp.premia(G, r, msg, random.Random(3)) == []  # secondo giro: già premiato
    assert msg.channel.send.await_count == 1


async def test_senza_premio_o_senza_votanti_non_si_scrive_niente():
    nid = await sondaggi_nativi_repo.crea(G, C, 5, "Domanda?", ["a", "b"], stato="aperto")
    r = await sondaggi_nativi_repo.prendi(nid)
    msg = _messaggio([_utente(1)])
    assert await sp.premia(G, r, msg) == []
    nid2 = await sondaggi_nativi_repo.crea(G, C, 5, "Domanda?", ["a", "b"], stato="aperto", premio=10)
    r2 = await sondaggi_nativi_repo.prendi(nid2)
    msg2 = _messaggio([])
    msg2.poll.answers = []
    assert await sp.premia(G, r2, msg2) == []
    msg.channel.send.assert_not_awaited()
