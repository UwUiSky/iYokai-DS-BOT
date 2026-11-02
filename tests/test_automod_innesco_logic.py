"""
tests/test_automod_innesco_logic.py
===================================
Innesco delle regole personali: regex RE2, liste di parole, domini, sole parole permesse.
Funzioni coperte: SPEC §6 (AMD-011, AMD-012, AMD-016, AMD-025)
"""

import time

from core.automod_innesco_logic import innesco_scatta


def test_regex_scatta_e_il_testo_lungo_non_blocca():
    r = {"tipo": "regex", "regex": [r"gratis\s+nitro", r"^\d{4}$"]}
    assert innesco_scatta(r, "regalo GRATIS   nitro qui".replace("GRATIS", "gratis"))
    assert not innesco_scatta(r, "ciao a tutti")
    cattiva = {"tipo": "regex", "regex": [r"(a+)+$"]}  # in re2 non esplode
    inizio = time.perf_counter()
    innesco_scatta(cattiva, "a" * 50_000 + "b")  # il testo si taglia a 4000 caratteri e re2 non va in backtracking
    assert time.perf_counter() - inizio < 1


def test_lista_di_parole_legge_le_varianti():
    r = {"tipo": "lista", "parole": ["gattaccio"]}
    assert innesco_scatta(r, "che G@TTACCIO")
    assert not innesco_scatta(r, "un gatto tranquillo")
    assert not innesco_scatta({"tipo": "lista", "parole": []}, "gattaccio")


def test_lista_con_nome_e_voci_insieme():
    liste = {"cattive": ("zucchino",)}
    r = {"tipo": "lista", "liste": ["cattive"], "parole": ["cetriolo"]}
    assert innesco_scatta(r, "uno zucchino", liste) and innesco_scatta(r, "un cetriolo", liste)
    assert not innesco_scatta({"tipo": "lista", "liste": ["mancante"]}, "zucchino", liste)


def test_domini_vietati_e_solo_permessi():
    vietati = {"tipo": "domini", "parole": ["evil.com"]}
    assert innesco_scatta(vietati, "vedi https://sub.evil.com/x")
    assert not innesco_scatta(vietati, "vedi https://bene.it")
    solo_yt = {"tipo": "domini", "modo": "permessi", "parole": ["youtube.com", "youtu.be"]}
    assert not innesco_scatta(solo_yt, "guarda https://www.youtube.com/watch?v=1 e https://youtu.be/2")
    assert innesco_scatta(solo_yt, "guarda https://vimeo.com/3")
    assert not innesco_scatta(solo_yt, "nessun link")


def test_sole_parole_permesse():
    r = {"tipo": "solo_permesse", "parole": ["sì", "no", "forse"]}
    assert not innesco_scatta(r, "Sì, no! forse")
    assert innesco_scatta(r, "sì ma anche boh")
    assert not innesco_scatta(r, "😀 123")  # niente parole: niente da giudicare


def test_innesco_vuoto_o_sconosciuto_non_scatta_e_sempre_scatta():
    assert not innesco_scatta({}, "qualsiasi cosa")
    assert not innesco_scatta({"tipo": "stato"}, "qualsiasi cosa")
    assert innesco_scatta({"tipo": "sempre"}, "")
