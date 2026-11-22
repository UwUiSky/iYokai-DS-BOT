"""
tests/test_collaudo.py
======================
Prova l'assistente di collaudo: analizzatore, stato, flusso con input finti,
issue con risposta finta di GitHub, token mai in chiaro, issue in sospeso.
Funzioni coperte: #94
"""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from scripts import collaudo as col

TOKEN = "ghp_SEGRETISSIMO123"
TESTO = """# Titolo

## Musica

- [ ] `MUS-001` — `/play` una canzone: parte l'audio.
  Poi `/skip`: passa alla successiva.
- [x] `MUS-002` — già provata.
- [ ] SEC-4/SEC-17 (#10, #14) — commit 599a2d4 — passi:
  1. Fai una cosa.

### Sotto

- [ ] `MUS-001` — doppione.

## Utilità

- [ ] `UTL-1` — `/ping`: risponde.
"""


@pytest.fixture
def ambiente(tmp_path):
    f = tmp_path / "VL.md"
    f.write_text(TESTO, encoding="utf-8")
    return f, col.Archivio(tmp_path / "c", token=TOKEN)


def risposte(*valori):
    it = iter(valori)

    def _leggi(_domanda):
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None
    return _leggi


def post_finto(numero=7, registro=None):
    def _post(url, token, payload):
        if registro is not None:
            registro.append((url, token, payload))
        return {"number": numero}
    return _post


def post_giu(url, token, payload):
    raise urllib.error.URLError(f"rete giù con {TOKEN}")


# ---- analizzatore

def test_analizza_codici_sezioni_e_fatte():
    p = col.analizza(TESTO)
    assert [x.id for x in p] == ["MUS-001", "MUS-002", "SEC-4/SEC-17", "MUS-001~2", "UTL-1"]
    assert p[0].sezione == "Musica" and p[3].sezione == "Sotto" and p[4].sezione == "Utilità"
    assert [x.fatta for x in p] == [False, True, False, False, False]
    assert "Poi `/skip`" in p[0].passi and p[0].riga == 5


# ---- stato e salto delle superate

def test_superata_non_si_ripropone_e_spunta_file(ambiente):
    f, arch = ambiente
    esegui = lambda *r: col.esegui(col.leggi_prove(f), arch, repo="a/b", token="",
                                   file_prove=f, leggi=risposte(*r))
    esegui("s", "n", "e")
    assert arch.carica()["MUS-001"]["esito"] == "superata"
    assert f.read_text().count("- [x] `MUS-001`") == 1
    prossime = col.da_proporre(col.leggi_prove(f), arch.carica())
    assert [x.id for x in prossime][0] == "SEC-4/SEC-17"


def test_saltata_torna_e_sezione_filtra(ambiente):
    f, arch = ambiente
    col.esegui(col.leggi_prove(f), arch, repo="", token="", file_prove=f,
               leggi=risposte("n", "e"))
    assert "MUS-001" not in arch.carica()
    ids = [x.id for x in col.da_proporre(col.leggi_prove(f), arch.carica(), "utilit")]
    assert ids == ["UTL-1"]


def test_non_modificare_lascia_il_file(ambiente):
    f, arch = ambiente
    prima = f.read_text()
    col.esegui(col.leggi_prove(f), arch, repo="", token="", file_prove=None,
               leggi=risposte("s", "n", "e"))
    assert f.read_text() == prima and arch.carica()["MUS-001"]["esito"] == "superata"


def test_risposta_non_valida_richiesta_ed_eof_esce(ambiente):
    f, arch = ambiente
    col.esegui(col.leggi_prove(f), arch, repo="", token="", file_prove=f,
               leggi=risposte("boh", "s", "forse", "n"))
    assert arch.carica()["MUS-001"]["esito"] == "superata"
    assert "SEC-4/SEC-17" not in arch.carica()  # EOF sulla seconda prova: esce


# ---- errore e issue

def test_errore_crea_issue_con_titolo_etichette_e_senza_token_nei_file(ambiente, capsys):
    f, arch = ambiente
    reg = []
    col.esegui(col.leggi_prove(f), arch, repo="own/rep", token=TOKEN, file_prove=f,
               leggi=risposte("s", "s", "il bot non risponde " + TOKEN, "e"),
               post=post_finto(42, reg), ver="abc1234")
    url, tok, payload = reg[0]
    assert url.endswith("/repos/own/rep/issues") and tok == TOKEN
    assert payload["title"].startswith("Prova live fallita: MUS-001 — ")
    assert payload["labels"] == ["verifica-live", "bug"]
    assert "abc1234" in payload["body"] and "Musica" in payload["body"]
    assert arch.carica()["MUS-001"]["issue"] == 42
    assert TOKEN not in capsys.readouterr().out
    for file in (arch.file_stato, arch.file_storico):
        assert TOKEN not in file.read_text()
    assert "- [ ] `MUS-001`" in f.read_text()  # un errore non spunta
    assert [x.id for x in col.da_proporre(col.leggi_prove(f), arch.carica())][0] != "MUS-001"


def test_testo_owner_troncato(ambiente):
    f, arch = ambiente
    reg = []
    col.esegui(col.leggi_prove(f), arch, repo="own/rep", token=TOKEN, file_prove=f,
               leggi=risposte("s", "s", "x" * 9000, "e"), post=post_finto(1, reg), ver="v")
    assert "x" * 4000 in reg[0][2]["body"] and "x" * 4001 not in reg[0][2]["body"]
    assert len(arch.carica()["MUS-001"]["descrizione"]) == 4000


def test_senza_token_o_rete_errore_salvato_poi_in_sospeso(ambiente, capsys):
    f, arch = ambiente
    prove = col.leggi_prove(f)
    col.esegui(prove, arch, repo="own/rep", token="", file_prove=f,
               leggi=risposte("s", "s", "rotto", "e"))
    assert arch.carica()["MUS-001"]["issue"] is None
    col.esegui(prove, arch, repo="own/rep", token=TOKEN, file_prove=f,
               leggi=risposte("s", "s", "rotto due", "e"), post=post_giu, ver="v")
    out = capsys.readouterr().out
    assert TOKEN not in out
    assert TOKEN not in arch.file_storico.read_text()
    reg = []
    n = col.invia_in_sospeso(arch, prove, "own/rep", TOKEN, post_finto(9, reg), "v")
    assert n >= 1 and arch.carica()["MUS-001"]["issue"] == 9
    assert "rotto" in reg[0][2]["body"]
    assert col.invia_in_sospeso(arch, prove, "own/rep", TOKEN, post_finto(10, reg), "v") == 0


def test_repo_non_valido_rifiutato(ambiente):
    p = col.leggi_prove(ambiente[0])[0]
    n, motivo = col.crea_issue(p, "x", "../../evil", TOKEN, post_finto(), "v")
    assert n is None and "COLLAUDO_REPO" in motivo


def test_http_error_senza_token_nel_messaggio():
    def post(url, token, payload):
        raise urllib.error.HTTPError(url, 403, TOKEN, {}, None)
    p = col.analizza(TESTO)[0]
    n, motivo = col.crea_issue(p, "x", "a/b", TOKEN, post, "v")
    assert n is None and "403" in motivo and TOKEN not in motivo


# ---- riepilogo, ripeti, storico, avviso

def test_riepilogo_ripeti_storico(ambiente, capsys):
    f, arch = ambiente
    col.esegui(col.leggi_prove(f), arch, repo="", token="", file_prove=f,
               leggi=risposte("s", "n", "s", "s", "boom", "e"))
    r = col.riepilogo(col.leggi_prove(f), arch.carica())
    assert "fatte 2, errori 1, da fare 2 (su 5)" in r
    assert "boom" in col.testo_storico(arch.storico())
    assert col.ripeti("MUS-001", col.leggi_prove(f), arch, f)
    assert "- [ ] `MUS-001`" in f.read_text()
    assert not col.ripeti("NON-ESISTE", col.leggi_prove(f), arch, f)
    assert "MUS-001" in [x.id for x in col.da_proporre(col.leggi_prove(f), arch.carica())]


def test_avviso_main():
    from core.collaudo_avviso import messaggio_collaudo
    assert messaggio_collaudo({"COLLAUDO": "1"}, True)
    assert messaggio_collaudo({"COLLAUDO": "1"}, False) is None
    assert messaggio_collaudo({}, True) is None
    assert messaggio_collaudo({"COLLAUDO": "0"}, True) is None


def test_file_vero_si_analizza():
    prove = col.leggi_prove()
    assert len(prove) > 600 and all(p.codice for p in prove)
    assert len({p.id for p in prove}) == len(prove)
