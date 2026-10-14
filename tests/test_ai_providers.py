"""
tests/test_ai_providers.py
==========================
Lettura dei fornitori dal `.env` (SPEC §25.1, §25.13, D19): solo chi dichiara
di non addestrare, https obbligatorio, chiave obbligatoria tranne in locale,
limiti letti, interruttore delle chiavi a pagamento. Nessuna rete.
"""

from core.ai_providers import leggi_fornitori, leggi_limiti, usa_chiavi_a_pagamento
from tests.support.ai_finto import chiave_finta


def _env(**kw):
    base = {"AI_FORNITORI": "alfa"}
    base.update(kw)
    return base


def test_senza_fornitori_niente_e_nessuno_scarto():
    assert leggi_fornitori({}) == ([], [])


def test_fornitore_valido_con_tipi_fascia_limiti():
    fornitori, scarti = leggi_fornitori(_env(
        AI_URL_ALFA="https://alfa.example/v1/", AI_KEY_ALFA=chiave_finta("alfa"), AI_ADDESTRA_ALFA="no",
        AI_TIPI_ALFA="chat, traduzione, inventato", AI_FASCIA_ALFA="media", AI_LIMITI_ALFA="rpm=30,rpg=1000,xx=4",
        AI_COSTO_ALFA="15",
    ))
    assert scarti == []
    f = fornitori[0]
    assert f.url == "https://alfa.example/v1"
    assert f.tipi == {"chat", "traduzione"}
    assert f.fascia == "media" and f.costo_cent_milione == 15
    assert f.limiti.rpm == 30 and f.limiti.rpg == 1000 and f.limiti.tpm is None
    assert chiave_finta("alfa") not in repr(f)


def test_chi_addestra_o_non_lo_dice_viene_scartato():
    for valore in (None, "si", ""):
        env = _env(AI_URL_ALFA="https://alfa.example/v1", AI_KEY_ALFA=chiave_finta("a"))
        if valore is not None:
            env["AI_ADDESTRA_ALFA"] = valore
        fornitori, scarti = leggi_fornitori(env)
        assert fornitori == [] and "D19" in scarti[0]


def test_http_e_chiave_obbligatori_tranne_in_locale():
    _, scarti = leggi_fornitori(_env(AI_URL_ALFA="http://alfa.example/v1", AI_KEY_ALFA="k", AI_ADDESTRA_ALFA="no"))
    assert "https" in scarti[0]
    _, scarti = leggi_fornitori(_env(AI_URL_ALFA="https://alfa.example/v1", AI_ADDESTRA_ALFA="no"))
    assert "AI_KEY_ALFA" in scarti[0]
    fornitori, _ = leggi_fornitori(_env(AI_URL_ALFA="http://127.0.0.1:11434/v1", AI_ADDESTRA_ALFA="no"))
    assert fornitori[0].chiave == ""


def test_nome_non_valido_scartato():
    _, scarti = leggi_fornitori({"AI_FORNITORI": "a b!"})
    assert "nome non valido" in scarti[0]


def test_limiti_e_interruttore_pagamento():
    assert leggi_limiti("rpm=0,tpg=-3,tpm=10").tpm == 10
    assert leggi_limiti(None).rpm is None
    assert usa_chiavi_a_pagamento({}) is False
    assert usa_chiavi_a_pagamento({"AI_USA_CHIAVI_PAGAMENTO": "si"}) is True
