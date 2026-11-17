"""
tests/test_leveling_guadagno_logica.py
======================================
#124 B3 (LIV-004, 006, 007, 017, 018, 021): formule dei livelli, XP a parola,
bonus impegno, prefissi di altri bot, elenco bianco dei canali. Solo logica pura.
"""

import pytest

from core.leveling_logic import (
    FORMULE,
    ConfigLivelli,
    LevelingSettings,
    did_level_up,
    ha_prefisso_ignorato,
    level_for_xp,
    prefisso_valido,
    stima_per_livello,
    xp_dopo_modifica,
    xp_for_level,
    xp_messaggio,
)


# ----------------------------------------------------------------- LIV-004
def test_liv004_la_formula_di_base_e_quella_di_prima():
    assert xp_for_level(10) == 5 * 100 + 500
    assert level_for_xp(1000) == level_for_xp(1000, 0, "classica")


@pytest.mark.parametrize("formula", FORMULE)
def test_liv004_ogni_formula_e_crescente_e_coerente(formula):
    assert xp_for_level(0, formula) == 0
    precedente = 0
    for livello in range(1, 120):
        richiesti = xp_for_level(livello, formula)
        assert richiesti > precedente
        # Il livello torna dall'XP, un punto sotto e un punto sopra la soglia.
        assert level_for_xp(richiesti, 0, formula) == livello
        assert level_for_xp(richiesti - 1, 0, formula) == livello - 1
        precedente = richiesti


def test_liv004_costante_costa_sempre_uguale():
    passi = {xp_for_level(n + 1, "costante") - xp_for_level(n, "costante") for n in range(50)}
    assert len(passi) == 1


def test_liv004_esponenziale_non_scoppia_con_xp_enormi():
    assert level_for_xp(10**15, 0, "esponenziale") < 400
    assert level_for_xp(10**15, 0, "lineare") > 1000
    assert level_for_xp(10**15, 3, "costante") == 3  # il tetto vale per ogni formula


def test_liv004_formula_sconosciuta_ricade_sulla_classica():
    assert xp_for_level(7, "boh") == xp_for_level(7, "classica")


def test_liv004_level_up_e_modifiche_usano_la_formula():
    sale, nuovo = did_level_up(0, xp_for_level(3, "costante"), 0, "costante")
    assert sale and nuovo == 3
    assert xp_dopo_modifica(0, "livello", 5, 0, "costante") == xp_for_level(5, "costante")
    stima = stima_per_livello(0, 4, 10, 60, 5, "costante")
    assert stima.xp_mancanti == xp_for_level(4, "costante")


# ----------------------------------------------------------------- LIV-006
def test_liv006_a_parola_conta_le_parole_da_tre_lettere():
    i = LevelingSettings(xp_modo="parola", xp_per_parola=2, parole_max=30)
    assert xp_messaggio(i, "ciao a tutti ok", False) == 2 * 2  # «ciao» e «tutti»
    assert xp_messaggio(i, "", False) == 0
    assert xp_messaggio(i, "a b c 1 2 3", False) == 0


def test_liv006_il_tetto_di_parole_e_quello_del_messaggio_valgono():
    i = LevelingSettings(xp_modo="parola", xp_per_parola=10, parole_max=100)
    testo = "parola " * 500
    assert xp_messaggio(i, testo, False) == 100  # mai oltre il massimo dei «testo»
    i2 = LevelingSettings(xp_modo="parola", xp_per_parola=1, parole_max=5)
    assert xp_messaggio(i2, testo, False) == 5


def test_liv006_modo_fisso_ignora_il_testo():
    assert xp_messaggio(LevelingSettings(text_xp=15), "ok", False) == 15


# ----------------------------------------------------------------- LIV-007
def test_liv007_bonus_per_messaggio_lungo_o_con_immagine():
    i = LevelingSettings(text_xp=15, bonus_impegno=5, impegno_caratteri=50)
    assert xp_messaggio(i, "x" * 49, False) == 15
    assert xp_messaggio(i, "x" * 50, False) == 20
    assert xp_messaggio(i, "ciao", True) == 20
    assert xp_messaggio(i, "x" * 500, True) == 20  # una volta sola


def test_liv007_bonus_spento_di_base():
    assert xp_messaggio(LevelingSettings(), "x" * 5000, True) == 15


# ----------------------------------------------------------------- LIV-018
def test_liv018_prefissi_di_altri_bot():
    assert ha_prefisso_ignorato("!play x", ("!", "?"))
    assert ha_prefisso_ignorato("   ?aiuto", ("!", "?"))
    assert not ha_prefisso_ignorato("ciao !", ("!", "?"))
    assert not ha_prefisso_ignorato("!play", ())


@pytest.mark.parametrize(
    "testo,atteso",
    [("!", "!"), ("  ?  ", "?"), (">>", ">>"), ("pls", "pls"), ("a", None), ("", None),
     ("a b", None), ("123456789", None), ("!​", None), ("!\n", "!"), ("`", "`")],
)
def test_liv018_prefisso_valido(testo, atteso):
    assert prefisso_valido(testo) == atteso


# ----------------------------------------------------------------- LIV-021
def test_liv021_elenco_bianco_dei_canali():
    solo = ConfigLivelli(
        impostazioni=LevelingSettings(canali_modo="solo_questi"), canali_esclusi=frozenset({5})
    )
    assert not solo.e_escluso([5], [])
    assert solo.e_escluso([6], [])
    assert not solo.e_escluso([9, 5], [])  # il thread vale come il canale madre


def test_liv021_elenco_vuoto_non_blocca_tutti():
    assert not ConfigLivelli(impostazioni=LevelingSettings(canali_modo="solo_questi")).e_escluso([6], [])


def test_liv021_un_ruolo_escluso_resta_escluso_anche_nel_canale_buono():
    solo = ConfigLivelli(
        impostazioni=LevelingSettings(canali_modo="solo_questi"),
        canali_esclusi=frozenset({5}), ruoli_esclusi=frozenset({1}),
    )
    assert solo.e_escluso([5], [1])


def test_liv021_di_base_l_elenco_esclude():
    c = ConfigLivelli(canali_esclusi=frozenset({5}))
    assert c.e_escluso([5], []) and not c.e_escluso([6], [])
