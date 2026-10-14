"""
tests/test_ai_cache_logic.py
============================
Cache delle risposte (SPEC §25.2, §25.11): stessa domanda, domanda molto
simile, scadenza, ambito del server separato dalla libreria comune.
"""

from core.ai_cache_logic import LIBRERIA_COMUNE, CacheAI, ambito, chiave, normalizza, somiglianza


def test_normalizza_e_chiave():
    assert normalizza("Ciao,   come VA?") == "ciao come va"
    assert chiave("chat", "x", "Ciao!") == chiave("chat", "x", "ciao")
    assert chiave("chat", "x", "ciao") != chiave("testo", "x", "ciao")


def test_trova_uguale_e_simile():
    c = CacheAI()
    c.metti(0, "chat", "istr", "come si banna un utente dal server", "usa /modban ban", ora=0)
    assert c.trova(0, "chat", "istr", "Come si banna un utente dal server?", ora=1) == "usa /modban ban"
    assert c.trova(0, "chat", "istr", "come si banna un utente dal server oggi", ora=1) == "usa /modban ban"  # 7/8
    assert c.trova(0, "chat", "istr", "come si banna un utente", ora=1) is None  # 5/7
    assert somiglianza("a b c d e f g", "a b c d e f g h") >= 0.85
    assert c.trova(0, "chat", "istr", "qualcosa di diverso", ora=1) is None
    assert c.trova(0, "chat", "altre istruzioni", "come si banna un utente dal server", ora=1) is None


def test_scadenza_e_ambiti():
    c = CacheAI(durata=10)
    c.metti(5, "chat", "", "domanda", "r", ora=0)
    assert c.trova(LIBRERIA_COMUNE, "chat", "", "domanda", ora=1) is None
    assert c.trova(5, "chat", "", "domanda", ora=11) is None
    c.metti(5, "chat", "", "domanda", "r", ora=20)
    c.svuota_ambito(5)
    assert len(c) == 0
    assert ambito(5, True) == 5 and ambito(5, False) == LIBRERIA_COMUNE and ambito(None, True) == LIBRERIA_COMUNE


def test_tetto_delle_voci():
    c = CacheAI(max_voci=2)
    for i in range(3):
        c.metti(0, "chat", "", f"d{i}", "r", ora=0)
    assert len(c) == 2
