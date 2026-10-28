"""
tests/test_ricerca_web.py
=========================
Ricerca assistita sul web (§25.45): configurazione, lettura dei risultati, link sospetti scartati, quota,
risposta con e senza AI. Nessuna rete: trasporto finto.
"""

import json
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from cogs.ai import _ricerca_web as cog
from core import ricerca_web_logic as logica
from core.ai_servizio import imposta_servizio_ai
from core.repositories.ai_repo import ai_repo
from core.ricerca_web import RicercaWeb, imposta_ricerca_web
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G, U = 8801, 8802
CONFIG = logica.ConfigRicerca("https://cerca.example/api", "chiave-finta-xxx", 2)


def test_config_solo_con_https_e_chiave():
    assert logica.leggi_config({}) is None
    assert logica.leggi_config({"RICERCA_WEB_URL": "http://x.example", "RICERCA_WEB_CHIAVE": "k"}) is None
    assert logica.leggi_config({"RICERCA_WEB_URL": "https://x.example"}) is None
    c = logica.leggi_config({"RICERCA_WEB_URL": "https://x.example", "RICERCA_WEB_CHIAVE": "k", "RICERCA_WEB_QUOTA_GIORNO": "7"})
    assert c.quota_giorno == 7


def test_risultati_nelle_due_forme_e_senza_roba_strana():
    a = logica.leggi_risultati({"results": [{"title": "T", "url": "https://a.example/x", "snippet": " uno\n due "}, {"title": "", "url": "x"}, 5]})
    assert [(r.titolo, r.estratto) for r in a] == [("T", "uno due")]
    b = logica.leggi_risultati({"web": {"results": [{"name": "N", "link": "https://b.example", "description": "d"}]}})
    assert b[0].titolo == "N" and logica.leggi_risultati("boh") == [] and logica.leggi_risultati({"results": "no"}) == []


def test_link_sospetti_e_non_https_scartati():
    r = [
        logica.Risultato("ok", "https://it.wikipedia.org/wiki/Roma", ""),
        logica.Risultato("http", "http://vecchio.example", ""),
        logica.Risultato("truffa", "https://discord-nitro-gratis.xyz/ritira", ""),
    ]
    assert [x.titolo for x in logica.risultati_sicuri(r)] == ["ok"]


def test_quota_giornaliera_riparte_il_giorno_dopo():
    q = logica.QuotaGiornaliera(2)
    oggi = date(2026, 10, 28)
    assert q.consenti(oggi) and q.consenti(oggi) and not q.consenti(oggi)
    assert q.consenti(oggi + timedelta(days=1))


async def test_cerca_rispetta_quota_e_errori():
    chiamate = []

    async def trasporto(config, domanda):
        chiamate.append(domanda)
        return {"results": [{"title": "T", "url": "https://a.example", "snippet": "s"}]}

    r = RicercaWeb(CONFIG, trasporto)
    assert len(await r.cerca("a")) == 1 and len(await r.cerca("b")) == 1 and await r.cerca("c") is None
    assert chiamate == ["a", "b"]
    assert await RicercaWeb(None).cerca("x") is None

    async def rotto(config, domanda):
        raise RuntimeError("giù")

    assert await RicercaWeb(CONFIG, rotto).cerca("x") is None


@pytest.fixture
def repo(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    yield ai_repo
    imposta_servizio_ai(None)
    imposta_ricerca_web(None)


def _inter():
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U))
    i.guild_id = G
    return i


async def _servizio(testo):
    async def trasporto(config, domanda):
        return {"results": [{"title": "Roma", "url": "https://it.wikipedia.org/wiki/Roma", "snippet": "capitale"}]}

    imposta_ricerca_web(RicercaWeb(CONFIG, trasporto))
    return testo


async def test_spenta_dice_che_serve_la_configurazione(repo):
    imposta_ricerca_web(RicercaWeb(None))
    i = _inter()
    await cog.risposta_con_ricerca(i, "capitale", G)
    assert cog.NON_ATTIVA == i.response.send_message.call_args.args[0]


async def test_con_ai_ferma_restano_i_risultati_e_con_ai_c_e_il_riassunto(repo):
    await _servizio(None)
    i = _inter()
    await cog.risposta_con_ricerca(i, "capitale d'italia", G)
    emb = i.followup.send.call_args.kwargs["embed"]
    assert "L'AI è ferma" in emb.description and "wikipedia" in emb.fields[0].value
    servizio, trasporto = servizio_finto(repo, fornitori=[fornitore()], trasporto=TrasportoFinto(risposte={"alfa": "Roma [1]."}))
    imposta_servizio_ai(servizio)
    await repo.registra_consenso(G, U, True)
    i = _inter()
    await cog.risposta_con_ricerca(i, "capitale d'italia", G)
    assert i.followup.send.call_args.kwargs["embed"].description == "Roma [1]."
    assert "capitale" in json.dumps(trasporto.chiamate[-1][1])
