"""
tests/test_invite_links_logic.py
================================
Parte pura dei link d'invito personali: nomi dell'indirizzo, tipo di ingresso, ruolo richiesto.
"""

import pytest

from core import invite_links_logic as l


@pytest.mark.parametrize("testo,atteso", [
    ("Anna Rossi", "anna-rossi"),
    ("Èlite__Gamer!!", "elite-gamer"),
    ("  --x--  ", "x"),
    ("日本語", ""),
    ("A" * 100, "a" * l.MAX_PARTE),
])
def test_slugifica(testo, atteso):
    assert l.slugifica(testo) == atteso


def test_slug_base_e_segnaposto():
    assert l.slug_base("Il Mio Server", "Anna") == "il-mio-server-anna"
    assert l.slug_base("日本", "🙂") == "server-membro"
    assert len(l.slug_base("s" * 100, "u" * 100)) <= l.MAX_SLUG


def test_suffisso_per_le_collisioni():
    assert l.slug_con_suffisso("a-b", 1) == "a-b"
    assert l.slug_con_suffisso("a-b", 3) == "a-b-3"
    lungo = "x" * l.MAX_SLUG
    assert len(l.slug_con_suffisso(lungo, 12)) <= l.MAX_SLUG and l.slug_con_suffisso(lungo, 12).endswith("-12")


@pytest.mark.parametrize("slug,ok", [
    ("il-mio-server-anna", True), ("ab", False), ("-abc", False), ("abc-", False),
    ("Abc-def", False), ("a/b-c", False), ("a" * 81, False), ("a" * 80, True),
])
def test_slug_valido(slug, ok):
    assert l.slug_valido(slug) is ok


def test_tipo_ingresso():
    assert l.tipo_ingresso(None, codice_vanity="v", link_personale=False) == l.TIPO_SCONOSCIUTO
    assert l.tipo_ingresso("abc", codice_vanity="v", link_personale=True) == l.TIPO_PERSONALE
    assert l.tipo_ingresso("v", codice_vanity="v", link_personale=False) == l.TIPO_VANITY
    assert l.tipo_ingresso("abc", codice_vanity=None, link_personale=False) == l.TIPO_NORMALE


def test_ruolo_ammesso():
    assert l.ruolo_ammesso(None, set())
    assert l.ruolo_ammesso(5, {5, 6})
    assert not l.ruolo_ammesso(5, {6})


def test_indirizzi():
    assert l.indirizzo_link("https://s.it/", "a-b") == "https://s.it/invito/a-b"
    assert l.indirizzo_discord("xyz") == "https://discord.gg/xyz"


def test_ogni_esito_ha_un_testo():
    for e in (l.MODULO_SPENTO, l.RUOLO_MANCANTE, l.NON_NEL_SERVER, l.INVITI_DISABILITATI,
              l.SENZA_PERMESSO, l.NESSUN_CANALE, l.ERRORE_DISCORD):
        assert l.testo_esito(e) != "Non è stato possibile."
