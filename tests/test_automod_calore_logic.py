"""
tests/test_automod_calore_logic.py
==================================
Calore delle regole AutoMod (AMD-068, 069, 072): somma, calo lineare, canale fermo, azioni alla soglia.
"""

from core import automod_calore_logic as lg
from core.automod_advanced_logic import CaloreConfig


def cfg(**k):
    return CaloreConfig(attivo=True, **k)


def test_il_calore_si_somma_e_cala_in_modo_lineare():
    t = lg.Termometro()
    assert t.aggiungi(1, 2, 40, 0.0, 6) == 40
    # dopo 5 minuti calano 30 punti, poi se ne aggiungono 20
    assert t.aggiungi(1, 2, 20, 300.0, 6) == 30
    assert t.valore(1, 2, 600.0, 6) == 0  # mai sotto zero


def test_utenti_e_server_diversi_non_si_mescolano():
    t = lg.Termometro()
    t.aggiungi(1, 2, 50, 0.0, 0)
    assert t.valore(1, 3, 0.0, 0) == 0
    assert t.valore(9, 2, 0.0, 0) == 0


def test_azzera_riparte_da_zero():
    t = lg.Termometro()
    t.aggiungi(1, 2, 50, 0.0, 0)
    t.azzera(1, 2)
    assert t.valore(1, 2, 0.0, 0) == 0


def test_la_memoria_ha_un_tetto():
    t = lg.Termometro(tetto=3)
    for u in range(10):
        t.aggiungi(1, u, 10, 0.0, 0)
    assert len(t) == 3


def test_canale_fermo_pesa_di_piu():
    f = lg.CanaliFermi()
    assert f.segna(1, 5, 0.0) is None  # primo messaggio visto
    assert f.segna(1, 5, 30 * 60.0) == 0.0
    c = cfg(fermo_minuti=10, fermo_peso=3)
    assert lg.punti(20, c, ultimo=0.0, adesso=30 * 60.0) == 60  # fermo da 30 minuti
    assert lg.punti(20, c, ultimo=25 * 60.0, adesso=30 * 60.0) == 20  # attivo
    assert lg.punti(20, c, ultimo=None, adesso=30 * 60.0) == 20  # canale mai visto: peso normale


def test_fermo_spento_con_zero_minuti():
    assert lg.punti(20, cfg(fermo_minuti=0, fermo_peso=3), ultimo=0.0, adesso=99999.0) == 20


def test_azioni_alla_soglia():
    a = lg.azioni_calore(cfg(warn=True, timeout_secondi=600))
    assert [x.t for x in a] == ["warn", "timeout", "log"]
    assert a[1].get("secondi") == 600
    assert [x.t for x in lg.azioni_calore(cfg(warn=False, timeout_secondi=0))] == ["log"]


def test_config_a_json_e_ritorno():
    c = cfg(soglia=150, calo_per_minuto=7, fermo_minuti=15, fermo_peso=4, timeout_secondi=900, warn=False)
    assert lg.config_da_json(lg.config_a_json(c)) == c
    assert lg.config_da_json({}) == CaloreConfig()
    assert lg.config_da_json({"soglia": -5, "fermo_peso": 999}).soglia == 100  # valori storti: di base
