"""
tests/test_ai_cost_logic.py
===========================
Conti dell'AI (SPEC §25.4, §25.14–§25.16, §25.63): token, costo, quote del
server, dell'utente (giorno e 30 giorni), della funzione, immagini della
settimana con quelle comprate, tetto di spesa, limite al minuto.
"""

from core.ai_cost_logic import (
    LimitatoreUtente, Quote, Uso, costo_millesimi, quota_superata, stima_token, tetto_raggiunto, usa_credito_immagine,
)


def test_token_e_costo():
    assert stima_token("") == 1 and stima_token("a" * 9) == 3
    assert costo_millesimi(0, 1000) == 0
    assert costo_millesimi(100, 1_000_000) == 100_000  # 100 centesimi


def test_quote_in_ordine():
    q = Quote(tetto_mensile_cent=1, utente_giorno=2, utente_30_giorni=5, funzione_giorno=3, immagini_settimana=1)
    assert quota_superata(q, Uso()) is None
    assert quota_superata(q, Uso(spesa_mese_millesimi=900), costo_previsto=200) == "tetto"
    assert quota_superata(q, Uso(utente_oggi=2)) == "quota_utente"
    assert quota_superata(q, Uso(utente_30_giorni=5)) == "quota_utente_30"
    assert quota_superata(q, Uso(funzione_oggi=3)) == "quota_funzione"
    assert quota_superata(q, Uso(immagini_settimana=1), immagine=True) == "quota_immagini"
    assert quota_superata(q, Uso(immagini_settimana=1, immagini_extra=2), immagine=True) is None
    assert usa_credito_immagine(q, Uso(immagini_settimana=1))


def test_zero_vuol_dire_senza_tetto_tranne_la_spesa():
    q = Quote(tetto_mensile_cent=0, utente_giorno=0, utente_30_giorni=0, funzione_giorno=0, immagini_settimana=0)
    assert quota_superata(q, Uso(utente_oggi=999, immagini_settimana=99), immagine=True) is None
    assert tetto_raggiunto(q, Uso())  # tetto 0: solo fornitori gratuiti


def test_limite_al_minuto():
    lim = LimitatoreUtente(al_minuto=2)
    assert lim.consenti(1, ora=0) and lim.consenti(1, ora=1)
    assert not lim.consenti(1, ora=2)
    assert lim.consenti(2, ora=2)
    assert lim.consenti(1, ora=61)
