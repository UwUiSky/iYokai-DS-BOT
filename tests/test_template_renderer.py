"""
tests/test_template_renderer.py
================================
Test di core/template_renderer.py — SEC-6: `render_template` deve
sostituire solo placeholder semplici `{nome}`, senza mai eseguire la
sintassi di formattazione di `str.format` (format spec, indici
posizionali, attributi/item lookup).
"""

from core.template_renderer import render_template


def test_sostituisce_placeholder_conosciuti():
    risultato = render_template("{label}: {title}", {"label": "Alert", "title": "Nuovo video"})
    assert risultato == "Alert: Nuovo video"


def test_placeholder_sconosciuto_resta_intatto():
    risultato = render_template("{label}: {titolo}", {"label": "Alert", "title": "X"})
    assert risultato == "Alert: {titolo}"


def test_format_spec_non_alloca_memoria_ed_e_ignorato():
    # Prima del fix, str.format su "{title:>999999999}" allocava ~1GB
    # di RAM e mandava in crash l'intero processo (tutti i bot
    # musicali + il Creator). Il rendering sicuro non deve MAI
    # interpretare la format spec: il placeholder con `:` non
    # corrisponde a `\{([a-z_]+)\}` e resta testo com'era.
    risultato = render_template("{title:>999999999}", {"title": "T"})
    assert risultato == "{title:>999999999}"
    assert len(risultato) < 100


def test_graffa_spaiata_non_solleva_eccezione():
    risultato = render_template("testo con { spaiato", {"label": "X"})
    assert risultato == "testo con { spaiato"


def test_output_troncato_a_2000_caratteri():
    valori = {"title": "A" * 5000}
    risultato = render_template("{title}", valori)
    assert len(risultato) == 2000


def test_nessun_placeholder_ritorna_testo_originale():
    assert render_template("nessun placeholder qui", {"label": "X"}) == "nessun placeholder qui"


def test_placeholder_ripetuto_viene_sostituito_ogni_volta():
    risultato = render_template("{label} - {label}", {"label": "Ciao"})
    assert risultato == "Ciao - Ciao"
