"""
tests/test_wiki_statica.py
==========================
Issue #147: la wiki dei comandi come sito statico, dall'albero dei comandi.
"""

import pytest

from core.command_search_logic import ComandoInfo, Opzione
from core.wiki_statica import cartella_del_comando, genera


def _c(percorso, descrizione="Fa <b>qualcosa</b>", opzioni=()):
    return ComandoInfo(percorso=percorso, descrizione=descrizione, gruppo=percorso.split()[0], opzioni=opzioni)


def test_cartelle_dei_comandi():
    assert str(cartella_del_comando("mod ban")) == "wiki/mod/ban"
    assert str(cartella_del_comando("ping")) == "wiki/ping"
    for brutto in ("", "../x", "a/b", "A b", "mod  ban", " mod", "mod ban ", "x.y"):
        with pytest.raises(ValueError):
            cartella_del_comando(brutto)


def test_sito_con_indice_pagine_e_css(tmp_path):
    comandi = [_c("mod ban", opzioni=(Opzione("utente", "Chi", True),)), _c("ping")]
    assert genera(comandi, tmp_path) == 2
    indice = (tmp_path / "wiki" / "index.html").read_text(encoding="utf-8")
    assert 'href="/wiki/mod/ban"' in indice and 'href="/wiki/ping"' in indice and "Fa &lt;b&gt;qualcosa" in indice
    assert 'action="/wiki"' not in indice and "/accedi" not in indice  # niente ricerca né accesso nel sito statico
    pagina = (tmp_path / "wiki" / "mod" / "ban" / "index.html").read_text(encoding="utf-8")
    assert "<code>/mod ban</code>" in pagina and "<code>utente</code>" in pagina and "<b>qualcosa" not in pagina
    assert (tmp_path / "static" / "pannello.css").stat().st_size > 0


def test_un_percorso_storto_ferma_la_generazione(tmp_path):
    with pytest.raises(ValueError):
        genera([_c("../fuori")], tmp_path)
    assert not (tmp_path.parent / "fuori").exists()


def test_il_pannello_vivo_ha_ancora_la_ricerca():
    import jinja2
    from core.wiki_statica import CARTELLA

    amb = jinja2.Environment(loader=jinja2.FileSystemLoader(CARTELLA / "templates"), autoescape=True)
    testo = amb.get_template("wiki.html").render(comandi=[], q="", utente_id=None, csrf="", messaggio=None, errore=False, proprietario=False)
    assert 'action="/wiki"' in testo and "/accedi" in testo
