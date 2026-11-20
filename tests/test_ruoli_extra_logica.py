"""
tests/test_ruoli_extra_logica.py
================================
Logica pura: ruolo personale (RUO-045), più ruoli per opzione (RUO-083), gruppo di menu (RUO-069),
immagini del benvenuto (RUO-012).
"""

import random
from datetime import datetime, timedelta, timezone

from core import ruoli_extra_logic as L
from core.role_menu_logic import Decisione


def test_RUO_045_nome_pulito():
    # RUO-045
    assert L.pulisci_nome_ruolo("@everyone") == "everyone"
    assert "@" not in L.pulisci_nome_ruolo("@here ciao <@&123> <@456>")
    assert L.pulisci_nome_ruolo("a​b‮c\x00d") == "a b c d"  # invisibili e controllo
    assert L.pulisci_nome_ruolo("   ") is None and L.pulisci_nome_ruolo("<@1>") is None
    assert len(L.pulisci_nome_ruolo("x" * 500)) == 100
    assert "`" not in L.pulisci_nome_ruolo("`x`")


def test_RUO_045_colore():
    # RUO-045
    assert L.valida_colore("#C24A3A") == 0xC24A3A and L.valida_colore("c24a3a") == 0xC24A3A
    assert L.valida_colore("#f00") == 0xFF0000
    for male in ("", "rosso", "#GGGGGG", "#12345", "0x123456", "#1234567"):
        assert L.valida_colore(male) is None


def test_RUO_045_pausa_sulle_modifiche():
    # RUO-045
    ora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert L.secondi_di_pausa(None, ora) == 0
    assert L.secondi_di_pausa(ora - timedelta(seconds=100), ora) == 200
    assert L.secondi_di_pausa(ora - timedelta(hours=1), ora) == 0


def test_RUO_045_tetti():
    # RUO-045
    assert L.puo_creare_ruolo_personale(249, 100) is None
    assert L.puo_creare_ruolo_personale(250, 100) is not None
    assert L.puo_creare_ruolo_personale(10, 250) is not None
    assert L.posizione_sotto_il_bot(10) == 9 and L.posizione_sotto_il_bot(1) == 1


def test_RUO_083_extra_e_tetto_di_cinque():
    # RUO-083
    assert L.puo_aggiungere_extra(3, False) is None
    assert L.puo_aggiungere_extra(4, False) is not None  # 1 + 4 = già 5
    assert L.puo_aggiungere_extra(4, True) is None  # sostituisce uno che c'è


def test_RUO_083_i_ruoli_in_piu_si_danno_e_si_tolgono_insieme():
    # RUO-083
    d = L.applica_extra_e_gruppo(Decisione(aggiungi=(1,)), extra={1: (2, 3)}, ruoli_membro=set())
    assert d.aggiungi == (1, 2, 3)
    d = L.applica_extra_e_gruppo(Decisione(togli=(1,)), extra={1: (2, 3)}, ruoli_membro={1, 2, 3})
    assert d.togli == (1, 2, 3)


def test_RUO_069_gruppo_toglie_il_vecchio():
    # RUO-069
    gruppo = frozenset({10, 20, 30})
    d = L.applica_extra_e_gruppo(Decisione(aggiungi=(10,)), extra={}, ruoli_gruppo=gruppo, ruoli_membro={20, 99})
    assert d.aggiungi == (10,) and d.togli == (20,)  # il 99 non è del gruppo
    d = L.applica_extra_e_gruppo(Decisione(togli=(10,)), extra={}, ruoli_gruppo=gruppo, ruoli_membro={10, 20})
    assert d.togli == (10,)  # chi toglie non perde altro


def test_RUO_069_due_scelte_nel_gruppo_si_rifiutano():
    # RUO-069
    d = L.applica_extra_e_gruppo(Decisione(aggiungi=(10, 20)), extra={}, ruoli_gruppo=frozenset({10, 20}), ruoli_membro=set())
    assert d.rifiuto


def test_RUO_069_un_ruolo_in_piu_dell_opzione_nuova_non_viene_tolto():
    # RUO-069
    d = L.applica_extra_e_gruppo(
        Decisione(aggiungi=(10,)), extra={10: (20,)}, ruoli_gruppo=frozenset({10, 20, 30}), ruoli_membro={20, 30}
    )
    assert d.aggiungi == (10, 20) and d.togli == (30,)


def test_RUO_069_nome_del_gruppo():
    # RUO-069
    assert L.pulisci_nome_gruppo("  Colori @everyone ") == "colori everyone"
    assert L.pulisci_nome_gruppo("@") is None


def test_RUO_012_scelta_casuale():
    # RUO-012
    assert L.scegli_immagine([]) is None
    visti = {L.scegli_immagine([1, 2, 3], random.Random(n)) for n in range(40)}
    assert visti == {1, 2, 3}
