"""
tests/test_ruoli_guidata_logica.py
==================================
RUO-047 (#123): passi della creazione guidata di un menu di ruoli.
"""

from core.ruoli_guidata_logic import MODALITA, StatoGuidato, emoji_da_testo, coppie_in_testo


def test_RUO_047_i_passi_vanno_in_ordine():
    # RUO-047
    s = StatoGuidato(autore_id=1)
    assert s.passo() == "modalita"
    s.modalita = "button"
    assert s.passo() == "testo"
    s.titolo = "Ruoli"
    assert s.passo() == "canale"
    s.canale_id = 5
    assert s.passo() == "ruoli"
    s.ruoli = [10, 11]
    assert s.passo() == "emoji"
    s.emoji_fatte = True
    assert s.passo() == "conferma"


def test_RUO_047_la_tendina_salta_le_emoji():
    # RUO-047
    s = StatoGuidato(autore_id=1, modalita="select", titolo="T", canale_id=5, ruoli=[10])
    assert s.passo() == "conferma"
    assert set(MODALITA) == {"button", "select", "reaction"}


def test_RUO_047_emoji_per_riga():
    # RUO-047
    assert emoji_da_testo("🎮\n🎨", 2, True) == (["🎮", "🎨"], None)
    assert emoji_da_testo("🎮", 2, False) == (["🎮", None], None)
    assert emoji_da_testo("🎮", 2, True)[1] is not None  # reazioni: tutte obbligatorie
    assert emoji_da_testo("ciao", 1, False)[1] is not None
    assert emoji_da_testo("🎮\n🎨\n🎵", 2, False)[1] is not None


def test_RUO_047_testo_delle_coppie():
    # RUO-047
    assert coppie_in_testo([10, 11], ["🎮", None]) == "🎮 <@&10>; <@&11>"
