"""
tests/test_ai_providers.py
==========================
Lettura dei fornitori dal `.env` (SPEC §25.1, §25.13, D19): solo chi dichiara
di non addestrare, https obbligatorio, chiave obbligatoria tranne in locale,
limiti letti, interruttore delle chiavi a pagamento. Nessuna rete.
"""

from core.ai_providers import ammetti_addestranti, env_con_file, leggi_fornitori, leggi_limiti, usa_chiavi_a_pagamento
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


def test_chi_non_dichiara_l_addestramento_viene_scartato():
    for valore in (None, "", "forse"):
        env = _env(AI_URL_ALFA="https://alfa.example/v1", AI_KEY_ALFA=chiave_finta("a"))
        if valore is not None:
            env["AI_ADDESTRA_ALFA"] = valore
        fornitori, scarti = leggi_fornitori(env)
        assert fornitori == [] and "AI_ADDESTRA_ALFA" in scarti[0]


def test_chi_addestra_si_segna_e_non_si_scarta_d55():
    env = _env(AI_URL_ALFA="https://alfa.example/v1", AI_KEY_ALFA=chiave_finta("a"), AI_ADDESTRA_ALFA="si")
    fornitori, scarti = leggi_fornitori(env)
    assert scarti == [] and fornitori[0].addestra is True
    env["AI_ADDESTRA_ALFA"] = "no"
    assert leggi_fornitori(env)[0][0].addestra is False


def test_interruttore_ammetti_addestranti_li_spegne_tutti():
    env = _env(AI_URL_ALFA="https://alfa.example/v1", AI_KEY_ALFA=chiave_finta("a"), AI_ADDESTRA_ALFA="si")
    assert ammetti_addestranti({}) is True
    assert ammetti_addestranti({"AI_AMMETTI_ADDESTRANO": "no"}) is False
    fornitori, scarti = leggi_fornitori({**env, "AI_AMMETTI_ADDESTRANO": "no"})
    assert fornitori == [] and "AI_AMMETTI_ADDESTRANO" in scarti[0]


def test_stessa_chiave_per_i_modelli_dello_stesso_servizio():
    """`gemini_lite` e `gemini_flash` usano `AI_KEY_GEMINI` se non hanno una chiave propria."""
    base = {"AI_FORNITORI": "gemini_lite,gemini_flash", "AI_KEY_GEMINI": chiave_finta("g")}
    for n in ("GEMINI_LITE", "GEMINI_FLASH"):
        base[f"AI_URL_{n}"] = "https://g.example/v1"
        base[f"AI_ADDESTRA_{n}"] = "si"
    base["AI_KEY_GEMINI_FLASH"] = chiave_finta("propria")
    fornitori, scarti = leggi_fornitori(base)
    assert scarti == [] and [f.chiave for f in fornitori] == [chiave_finta("g"), chiave_finta("propria")]


def test_file_dei_fornitori_accanto_al_env(tmp_path):
    file = tmp_path / "ai_fornitori.env"
    file.write_text(
        "AI_FORNITORI=alfa\nAI_URL_ALFA=https://alfa.example/v1\nAI_ADDESTRA_ALFA=si\nAI_KEY_ALFA=\n", encoding="utf-8"
    )
    env = env_con_file({"AI_KEY_ALFA": chiave_finta("a"), "AI_FORNITORI": ""}, file)
    assert env["AI_FORNITORI"] == "alfa" and env["AI_KEY_ALFA"] == chiave_finta("a")  # l'ambiente vince
    assert leggi_fornitori(env)[0][0].nome == "alfa"
    assert env_con_file({"X": "1"}, tmp_path / "manca.env") == {"X": "1"}


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
