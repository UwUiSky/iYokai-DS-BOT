"""
tests/test_automod_innesco_logic.py
===================================
Innesco delle regole personali: regex RE2, liste di parole, domini, sole parole permesse.
Funzioni coperte: SPEC §6 (AMD-011, AMD-012, AMD-016, AMD-025)
"""

import time

import pytest

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


# ---------------------------------------------------------------- ruoli e casi dalla finestra (A9, pannello)


def test_filtro_ruoli_legge_id_e_menzioni():
    from core.automod_innesco_logic import leggi_filtro_evento

    f = leggi_filtro_evento("ruolo_dato", "123456789012345678, <@&223456789012345678> 123456789012345678")
    assert f == {"ruoli": [123456789012345678, 223456789012345678]}
    assert leggi_filtro_evento("ruolo_tolto", "  ") == {}  # vuoto: qualsiasi ruolo


def test_filtro_ruoli_rifiuta_nomi_e_ruoli_di_altri_server():
    """Un nome al posto dell'ID non deve diventare «qualsiasi ruolo»; un ruolo che il server non ha si rifiuta."""
    import pytest

    from core.automod_innesco_logic import leggi_filtro_evento
    from core.automod_regole_logic import RegolaNonValida

    with pytest.raises(RegolaNonValida):
        leggi_filtro_evento("ruolo_dato", "@Moderatori")
    with pytest.raises(RegolaNonValida):
        leggi_filtro_evento("ruolo_dato", "123456789012345678 Moderatori")
    del_server = {123456789012345678}.__contains__
    assert leggi_filtro_evento("ruolo_dato", "123456789012345678", del_server) == {"ruoli": [123456789012345678]}
    with pytest.raises(RegolaNonValida):
        leggi_filtro_evento("ruolo_dato", "<@&223456789012345678>", del_server)


def test_filtro_casi_legge_i_tipi_in_minuscolo():
    from core.automod_innesco_logic import leggi_filtro_evento

    assert leggi_filtro_evento("caso", "Warn, ban  mute") == {"casi": ["warn", "ban", "mute"]}
    assert leggi_filtro_evento("caso", "") == {}


def test_filtro_per_altri_eventi_e_ignorato():
    from core.automod_innesco_logic import leggi_filtro_evento

    assert leggi_filtro_evento("messaggio", "123456789012345678") == {}
    assert leggi_filtro_evento("ingresso", "warn") == {}


def test_filtro_scrive_il_testo_della_finestra():
    from core.automod_innesco_logic import scrivi_filtro_evento

    assert scrivi_filtro_evento("caso", {"tipo": "sempre", "casi": ["warn", "ban"]}) == "warn, ban"
    assert scrivi_filtro_evento("ruolo_dato", {"ruoli": [1, 2]}) == "1, 2"
    assert scrivi_filtro_evento("messaggio", {}) == ""


# ---------------------------------------------------------------- soglie per canale (AMD-008)


def test_soglia_canale_legge_numero_e_secondi():
    from core.automod_innesco_logic import leggi_soglia_canale, parametri_soglia_canale, scrivi_soglia_canale

    assert leggi_soglia_canale("12/8") == {"numero": 12, "secondi": 8}
    assert leggi_soglia_canale(" 5 / 30 ") == {"numero": 5, "secondi": 30}
    assert leggi_soglia_canale("") == {}
    assert parametri_soglia_canale({"tipo": "soglia_canale"}) == (10, 10)
    assert parametri_soglia_canale({"numero": 3, "secondi": 60}) == (3, 60)
    assert scrivi_soglia_canale({"numero": 3, "secondi": 60}) == "3/60"
    assert scrivi_soglia_canale({}) == ""


@pytest.mark.parametrize("testo", ["abc", "1/2/3", "0/10", "10/0", "10/99999", "20000/10", "-1/5"])
def test_soglia_canale_storta(testo):
    from core.automod_innesco_logic import leggi_soglia_canale
    from core.automod_regole_logic import RegolaNonValida

    with pytest.raises(RegolaNonValida):
        leggi_soglia_canale(testo)
