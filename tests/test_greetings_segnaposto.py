"""
tests/test_greetings_segnaposto.py
==================================
RUO-018..021 (#123): segnaposto in più nei messaggi di benvenuto: numero ordinale,
ID dell'utente, nome visualizzato, ID del server.
"""

from core.greetings_logic import MAX_MESSAGE_LENGTH, lunghezza_dopo_segnaposto, render_template


def _r(testo, **kw):
    base = dict(user_mention="<@5>", username="mario", server_name="S", member_count=1234)
    base.update(kw)
    return render_template(testo, **base)


def test_ordinale_con_punto_delle_migliaia():
    assert _r("sei il {ordinal}") == "sei il 1.234º"
    assert _r("{ordinal}", member_count=7) == "7º"


def test_id_utente_nome_visualizzato_e_id_server():
    out = _r("{userid} {displayname} {serverid}", user_id=5, display_name="Mario Rossi", server_id=99)
    assert out == "5 Mario Rossi 99"


def test_segnaposto_nuovi_senza_dati_restano_scritti():
    assert _r("{userid}") == "{userid}"


def test_la_lunghezza_peggiore_conta_i_segnaposto_nuovi():
    assert lunghezza_dopo_segnaposto("{userid}", "S", 1) >= 20
    assert lunghezza_dopo_segnaposto("{displayname}", "S", 1) >= 32
    assert lunghezza_dopo_segnaposto("{serverid}", "S", 1) >= 20
    assert lunghezza_dopo_segnaposto("{displayname}" * 80, "S", 1) > MAX_MESSAGE_LENGTH
