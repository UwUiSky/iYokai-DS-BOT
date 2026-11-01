"""
tests/test_desktop_prog_presenza.py
===================================
SPEC D.2, D.3, D.4 (#108): campi della rich presence, profili salvati, rotazione.
"""

import json
from threading import Event

import pytest

from desktop.iyokai_desktop import presenza as p


def test_costruisci_completo():
    a = p.costruisci(
        {"details": "Gioco", "state": "In partita", "large_image": "logo", "large_text": "Il logo", "small_image": "https://x.example/a.png",
         "bottoni": [("Sito", "https://iyokai.example")], "timer": "avvio"},
        adesso=lambda: 1000.9,
    )
    assert a == {
        "details": "Gioco", "state": "In partita",
        "assets": {"large_image": "logo", "small_image": "https://x.example/a.png", "large_text": "Il logo"},
        "buttons": [{"label": "Sito", "url": "https://iyokai.example"}], "timestamps": {"start": 1000},
    }
    assert p.costruisci({"details": "ab", "timer": "90"}, adesso=lambda: 10)["timestamps"] == {"end": 100}


@pytest.mark.parametrize("campi,codice", [
    ({}, "attivita_vuota"), ({"details": "a"}, "testo_lunghezza"), ({"state": "x" * 129}, "testo_lunghezza"),
    ({"details": "ok", "large_image": "http://x/a.png"}, "immagine_non_valida"),
    ({"details": "ok", "large_image": "con spazio"}, "immagine_non_valida"),
    ({"details": "ok", "bottoni": [("a", "https://x")] * 3}, "troppi_bottoni"),
    ({"details": "ok", "bottoni": [("a", "http://x")]}, "bottone_non_valido"),
    ({"details": "ok", "bottoni": [("", "https://x")]}, "bottone_non_valido"),
    ({"details": "ok", "bottoni": [("x" * 33, "https://x")]}, "bottone_non_valido"),
    ({"details": "ok", "bottoni": ["solo"]}, "bottone_non_valido"),
    ({"details": "ok", "timer": "zero"}, "timer_non_valido"), ({"details": "ok", "timer": "0"}, "timer_non_valido"),
])
def test_costruisci_rifiuta(campi, codice):
    with pytest.raises(p.ErrorePresenza) as e:
        p.costruisci(campi)
    assert e.value.codice == codice


def test_profili_salva_elenca_elimina(tmp_path):
    a = p.ArchivioProfili(tmp_path / "x" / "profili.json")
    assert a.nomi() == [] and a.carica("lavoro") is None
    a.salva("lavoro", {"details": "Al lavoro"})
    a.salva("Gioco 1", {"details": "Gioco"})
    assert a.nomi() == ["Gioco 1", "lavoro"] and a.carica("lavoro") == {"details": "Al lavoro"}
    assert a.elimina("lavoro") and not a.elimina("lavoro")
    assert not list((tmp_path / "x").glob("*.tmp"))


def test_profili_rifiuta_nomi_campi_e_troppi(tmp_path):
    a = p.ArchivioProfili(tmp_path / "p.json")
    for nome in ("", "a/b", "x" * 41):
        with pytest.raises(p.ErrorePresenza, match="nome_profilo_non_valido"):
            a.salva(nome, {"details": "ok"})
    with pytest.raises(p.ErrorePresenza):
        a.salva("vuoto", {})
    for n in range(p.MAX_PROFILI):
        a.salva(f"p{n}", {"details": "ok"})
    with pytest.raises(p.ErrorePresenza, match="troppi_profili"):
        a.salva("uno_di_troppo", {"details": "ok"})
    a.salva("p0", {"details": "cambiato"})  # sostituire un profilo esistente è sempre possibile


def test_profili_file_rotto_si_ignora(tmp_path):
    f = tmp_path / "p.json"
    f.write_text("{non json", encoding="utf-8")
    assert p.ArchivioProfili(f).nomi() == []
    f.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert p.ArchivioProfili(f).nomi() == []


class _Cliente:
    def __init__(self):
        self.stati = []

    def imposta_attivita(self, a):
        self.stati.append(a)


def test_rotazione_in_cerchio_e_toglie_lo_stato_alla_fine():
    c = _Cliente()
    fatti = p.ruota(c, [{"details": "uno1"}, {"details": "due2"}], 20, Event(), giri=3)
    assert fatti == 3
    assert [s and s["details"] for s in c.stati] == ["uno1", "due2", "uno1", None]


def test_rotazione_si_ferma_e_rifiuta_i_limiti():
    c = _Cliente()
    ferma = Event()
    ferma.set()
    assert p.ruota(c, [{"details": "uno1"}, {"details": "due2"}], 20, ferma) == 0
    with pytest.raises(p.ErrorePresenza, match="intervallo_troppo_corto"):
        p.ruota(c, [{"details": "uno1"}, {"details": "due2"}], 19, Event())
    with pytest.raises(p.ErrorePresenza, match="servono_due_stati"):
        p.ruota(c, [{"details": "uno1"}], 20, Event())
    with pytest.raises(p.ErrorePresenza, match="testo_lunghezza"):
        p.ruota(c, [{"details": "uno1"}, {"details": "x"}], 20, Event())
