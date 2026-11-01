"""
tests/test_spiriti_logic.py
===========================
Spirito Yokai e frammenti di lore (§25.71, §25.72): solo formule, nomi e testi pronti.
"""

from core import spiriti_logic as s


def test_affinita_normalizzata_e_con_tetto():
    a = s.affinita(s.Misure(messaggi=150, minuti_voce=99999, giorni_attivi=0, monete=-5))
    assert a == {"scrittura": 0.5, "voce": 1.0, "costanza": 0.0, "monete": 0.0}


def test_spirito_dominante_e_nessuno_senza_attivita():
    assert s.spirito_dominante(s.affinita(s.Misure())) is None
    assert s.ASSI[s.spirito_dominante(s.affinita(s.Misure(messaggi=300, minuti_voce=60)))] == "scrittura"
    pari = s.affinita(s.Misure(messaggi=300, minuti_voce=600))
    assert s.ASSI[s.spirito_dominante(pari)] == "scrittura"  # a pari valore vince il primo


def test_legame_da_zero_a_cinque_e_titolo():
    assert s.livello_legame(s.affinita(s.Misure())) == 0
    assert s.livello_legame(s.affinita(s.Misure(300, 600, 20, 2000))) == 5
    assert s.titolo("Kitsune", 4) == "Custode di Kitsune" and s.titolo("X", 99) == "Eletto di X"
    assert s.barra(0.5) == "█████░░░░░"


def test_ogni_tema_ha_quattro_spiriti_come_gli_assi():
    for tema, spiriti in s.SPIRITI.items():
        assert len(spiriti) == len(s.ASSI), tema
    assert s.spiriti_del_tema("boh") == s.SPIRITI["yokai"]


def test_frammenti_sbloccati_dai_conteggi_e_non_due_volte():
    m = s.Misure(messaggi=60, minuti_voce=10, giorni_attivi=5, monete=0)
    assert [f.codice for f in s.frammenti_da_sbloccare(m, set())] == ["voce_antica", "costanza"]
    assert [f.codice for f in s.frammenti_da_sbloccare(m, {"voce_antica"})] == ["costanza"]
    for f in s.FRAMMENTI:
        assert f.codice in s.testo_frammento(f, "x") or s.testo_frammento(f, "un luogo")
    assert len(s.CODICI) == 6 and "trofeo_boss" in s.CODICI and "dungeon" in s.CODICI
