"""
tests/test_automod_eventi_logic.py
==================================
Innesco delle regole sugli eventi che non sono messaggi (AMD-009/010/017/018/075) e freni contro i giri a vuoto.
"""

import pytest

from core import automod_eventi_logic as lg
from core.automod_regole_logic import RegolaNonValida, innesco_da_json

CH = (1, 2, "p:1")


def scatta(evento, innesco, dati=None, *, conteggi=None, ora=0.0, liste=None):
    return lg.innesco_evento_scatta(evento, innesco, dati or lg.DatiEvento(), liste, conteggi or lg.Conteggi(), CH, ora)


def test_spostamenti_vocali_scattano_al_numero_nella_finestra():
    c = lg.Conteggi()
    innesco = {"tipo": "spostamenti_vocali", "numero": 3, "secondi": 10}
    assert [scatta("vocale", innesco, conteggi=c, ora=t) for t in (0, 3, 6)] == [False, False, True]


def test_spostamenti_fuori_dalla_finestra_non_si_sommano():
    c = lg.Conteggi()
    innesco = {"tipo": "spostamenti_vocali", "numero": 3, "secondi": 10}
    assert not any(scatta("vocale", innesco, conteggi=c, ora=t) for t in (0, 20, 40))


def test_spostamenti_valori_di_base():
    c = lg.Conteggi()
    risultati = [scatta("vocale", {"tipo": "spostamenti_vocali"}, conteggi=c, ora=t) for t in range(5)]
    assert risultati == [False] * 4 + [True]


def test_thread_a_raffica_di_base_tre_in_cinque_minuti():
    c = lg.Conteggi()
    assert [scatta("thread", {"tipo": "thread_raffica"}, conteggi=c, ora=t) for t in (0, 100, 200)] == [False, False, True]
    assert not scatta("thread", {"tipo": "thread_raffica"}, conteggi=lg.Conteggi(), ora=0)


def test_le_chiavi_diverse_hanno_conteggi_diversi():
    c = lg.Conteggi()
    innesco = {"tipo": "thread_raffica", "numero": 2, "secondi": 60}
    assert not lg.innesco_evento_scatta("thread", innesco, lg.DatiEvento(), None, c, (1, 10, "p:1"), 0)
    assert not lg.innesco_evento_scatta("thread", innesco, lg.DatiEvento(), None, c, (1, 11, "p:1"), 1)


def test_nome_con_lista_e_con_regex():
    liste = {}
    assert scatta("nome", {"tipo": "nome", "parole": ["scam"]}, lg.DatiEvento(testo="Free SCAM nitro"), liste=liste)
    assert not scatta("nome", {"tipo": "nome", "parole": ["scam"]}, lg.DatiEvento(testo="Mario"), liste=liste)
    assert scatta("nome", {"tipo": "nome", "regex": [r"discord\.gg/\w+"]}, lg.DatiEvento(testo="vieni su discord.gg/abc"))
    assert not scatta("nome", {"tipo": "nome", "regex": [r"discord\.gg/\w+"]}, lg.DatiEvento(testo="Mario"))


def test_nome_con_lista_con_nome_del_server():
    assert scatta("nome", {"tipo": "lista", "liste": ["brutte"]}, lg.DatiEvento(testo="sei brutto?"), liste={"brutte": ("brutto",)})


def test_stato_come_il_nome():
    assert scatta("stato", {"tipo": "stato", "parole": ["gratis"]}, lg.DatiEvento(testo="Nitro gratis qui"))
    assert not scatta("stato", {"tipo": "stato", "parole": ["gratis"]}, lg.DatiEvento(testo="ciao"))


def test_nome_vuoto_non_scatta():
    assert not scatta("nome", {"tipo": "nome", "parole": ["x"]}, lg.DatiEvento(testo=""))


def test_ingresso_e_uscita_solo_con_sempre():
    assert scatta("ingresso", {"tipo": "sempre"}) and scatta("uscita", {"tipo": "sempre"})
    assert not scatta("ingresso", {"tipo": "regex", "regex": ["a"]})
    assert not scatta("ingresso", {})


def test_ruolo_con_filtro_dei_ruoli():
    assert scatta("ruolo_dato", {"tipo": "sempre"}, lg.DatiEvento(ruolo_id=5))
    assert scatta("ruolo_tolto", {"tipo": "sempre", "ruoli": [5, 6]}, lg.DatiEvento(ruolo_id=5))
    assert not scatta("ruolo_dato", {"tipo": "sempre", "ruoli": [6]}, lg.DatiEvento(ruolo_id=5))


def test_caso_con_filtro_dei_tipi():
    assert scatta("caso", {"tipo": "sempre", "casi": ["ban", "kick"]}, lg.DatiEvento(tipo_caso="ban"))
    assert not scatta("caso", {"tipo": "sempre", "casi": ["ban"]}, lg.DatiEvento(tipo_caso="warn"))
    assert scatta("caso", {"tipo": "sempre"}, lg.DatiEvento(tipo_caso="warn"))


def test_innesco_di_un_altro_evento_non_scatta():
    assert not scatta("vocale", {"tipo": "thread_raffica"})
    assert not scatta("thread", {"tipo": "spostamenti_vocali"})
    assert not scatta("messaggio", {"tipo": "sempre"})


def test_effetti_del_bot_si_ignorano_per_30_secondi():
    e = lg.Effetti()
    e.segna(1, 2, "ruolo", 77, 100.0)
    assert e.e_nostro(1, 2, "ruolo", 77, 120.0)
    assert not e.e_nostro(1, 2, "ruolo", 77, 131.0)
    assert not e.e_nostro(1, 2, "ruolo", 78, 110.0)
    assert not e.e_nostro(1, 3, "ruolo", 77, 110.0)


def test_al_massimo_tre_regole_per_persona_ed_evento_ogni_10_secondi():
    lim = lg.LimiteRegole()
    assert [lim.consente(1, 2, "ruolo_dato", t) for t in (0, 1, 2, 3)] == [True, True, True, False]
    assert lim.consente(1, 2, "uscita", 3)
    assert lim.consente(1, 9, "ruolo_dato", 3)
    assert lim.consente(1, 2, "ruolo_dato", 13)


def test_ruoli_e_casi_nell_innesco_si_validano():
    assert innesco_da_json({"tipo": "sempre", "ruoli": [5, 5, 6], "casi": ["BAN"]}) == {"tipo": "sempre", "ruoli": [5, 6], "casi": ["ban"]}
    with pytest.raises(RegolaNonValida):
        innesco_da_json({"tipo": "sempre", "ruoli": list(range(1, 30))})
    with pytest.raises(RegolaNonValida):
        innesco_da_json({"tipo": "sempre", "casi": ["x"] * 11})
    with pytest.raises(RegolaNonValida):
        innesco_da_json({"tipo": "sempre", "ruoli": ["a"]})
