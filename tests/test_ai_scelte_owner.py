"""
tests/test_ai_scelte_owner.py
=============================
Scelte dell'owner sopra il .env (§25.82, §25.94): modello, fascia, tipi, tetto di lunghezza. Database vero.
"""

import pytest

from core import ai_override_logic as ov
from core.ai_servizio import RichiestaAI, imposta_scelte_owner, imposta_servizio_ai
from core.repositories.ai_repo import ai_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto

G, U = 9601, 9602


@pytest.fixture
def servizio(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    s, t = servizio_finto(ai_repo, fornitori=[fornitore("alfa"), fornitore("beta", tipi=("chat",))], trasporto=TrasportoFinto(risposte={"alfa": "x" * 50, "beta": "y"}))
    imposta_servizio_ai(s)
    yield s, t
    imposta_servizio_ai(None)


def test_lettura_ignora_valori_rovinati():
    assert ov.leggi("non json") == {} and ov.leggi("[1]") == {}
    assert ov.leggi('{"a": {"fascia": "enorme", "modello": "ok-1", "tipi": ["chat", "boh"]}}') == {"a": {"modello": "ok-1", "tipi": ["chat"]}}


def test_errori_di_scelta():
    assert ov.errore_scelta("modello cattivo; drop", None, None)
    assert ov.errore_scelta(None, "enorme", None) and ov.errore_scelta(None, None, "chat,boh")
    assert ov.errore_scelta("gpt-4o-mini", "alta", "chat,codice") is None
    assert ov.tetto_valido("50") is None and ov.tetto_valido("800") == 800 and ov.tetto_valido("x") is None


async def test_modello_fascia_e_tipi_si_applicano_a_caldo(servizio):
    s, _ = servizio
    assert await imposta_scelte_owner("alfa", "nuovo-modello", "alta", "codice,chat", user_id=1) is None
    await s._leggi_scelte_owner()
    alfa = next(f for f in s.motore.fornitori if f.nome == "alfa")
    assert (alfa.modello, alfa.fascia, alfa.tipi) == ("nuovo-modello", "alta", frozenset({"codice", "chat"}))
    assert s.motore.sa_fare("codice")


async def test_fornitore_sconosciuto_e_scelte_sbagliate(servizio):
    assert await imposta_scelte_owner("zeta", "m") == "Fornitore sconosciuto."
    assert await imposta_scelte_owner("alfa", None, "enorme") is not None
    assert await imposta_scelte_owner(tetto_token=50) is not None


async def test_tetto_di_lunghezza_limita_le_risposte(servizio):
    s, t = servizio
    await ai_repo.registra_consenso(G, U, True)
    assert await imposta_scelte_owner(tetto_token=100, user_id=1) is None
    await s.richiedi(RichiestaAI(user_id=U, funzione="chiedi", tipo="chat", testo="ciao", guild_id=G, riusa=False))
    assert s.tetto_token == 100
    assert await imposta_scelte_owner(togli_tetto=True) is None
    await s._leggi_scelte_owner()
    assert s.tetto_token is None


async def test_dopo_un_riavvio_le_scelte_valgono_dalla_prima_richiesta(servizio, clean_db):
    """Un tipo dato dall'owner (codice a «beta») vale anche per la prima richiesta di un servizio appena creato."""
    await ai_repo.registra_consenso(G, U, True)
    assert await imposta_scelte_owner("beta", None, None, "chat,codice", user_id=1) is None
    nuovo, _ = servizio_finto(ai_repo, fornitori=[fornitore("beta", tipi=("chat",))], trasporto=TrasportoFinto(risposte={"beta": "y"}))
    imposta_servizio_ai(nuovo)
    risposta = await nuovo.richiedi(RichiestaAI(user_id=U, funzione="chiedi", tipo="codice", testo="ciao", guild_id=G, riusa=False))
    assert risposta.testo == "y"
