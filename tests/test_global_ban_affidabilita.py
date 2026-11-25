"""
tests/test_global_ban_affidabilita.py
=====================================
Scala di affidabilità del ban globale (blocco A, voce 1): server piccolo o nuovo, ritmo dei ban,
raid o nuke in corso, qualità del motivo, conferme, ban automatico solo sopra la soglia alta.
"""

from core import global_ban_logic as lg

BASE = dict(membri=300, giorni_server=400, giorni_bot=90, ban_ultima_ora=1, ban_oggi=2,
            motivo="Ha scritto nel canale trappola e ha mandato link malevoli", con_prova=True, conferme=0)


def _p(**kw):
    return lg.punteggio_affidabilita(**{**BASE, **kw})


def test_server_piccolo_o_bot_nuovo_vale_zero():
    assert _p(membri=10)[0] == 0
    assert _p(giorni_bot=2)[0] == 0


def test_server_buono_supera_la_soglia_minima():
    assert _p()[0] >= lg.SOGLIA_MINIMA


def test_motivo_vuoto_o_generico_pesa_meno():
    assert _p(motivo="")[0] < _p()[0]
    assert _p(motivo="Spam trap triggered")[0] < _p()[0]
    assert not lg.motivo_di_qualita("  SPAM ")


def test_la_prova_e_le_conferme_alzano_il_punteggio():
    assert _p(con_prova=False)[0] < _p()[0]
    assert _p(conferme=2, con_prova=False)[0] > _p(con_prova=False)[0]


def test_ritmo_alto_abbassa_sotto_la_soglia():
    assert _p(ban_ultima_ora=lg.MAX_BAN_ORA + 1)[0] < lg.SOGLIA_MINIMA


def test_il_punteggio_resta_tra_0_e_100():
    assert _p(conferme=50, giorni_server=9999, membri=10**6)[0] <= 100


def test_durante_un_raid_o_un_nuke_non_si_propaga():
    assert lg.decisione_propagazione(punteggio=100, raid_o_nuke_in_corso=True, invia=True, ban_oggi=0) == "attacco"


def test_spento_tetto_e_punteggio():
    d = lg.decisione_propagazione
    assert d(punteggio=100, raid_o_nuke_in_corso=False, invia=False, ban_oggi=0) == "spento"
    assert d(punteggio=100, raid_o_nuke_in_corso=False, invia=True, ban_oggi=lg.MAX_BAN_GIORNO + 1) == "tetto"
    assert d(punteggio=lg.SOGLIA_MINIMA - 1, raid_o_nuke_in_corso=False, invia=True, ban_oggi=0) == "punteggio"
    assert d(punteggio=lg.SOGLIA_MINIMA, raid_o_nuke_in_corso=False, invia=True, ban_oggi=0) is None


def test_automatico_solo_se_scelto_e_sopra_la_soglia_alta():
    m = lg.modo_di_arrivo
    assert m(punteggio=100, il_server_vuole_automatico=False) == "proposta"
    assert m(punteggio=lg.SOGLIA_AUTOMATICA - 1, il_server_vuole_automatico=True) == "proposta"
    assert m(punteggio=lg.SOGLIA_AUTOMATICA, il_server_vuole_automatico=True) == "automatico"
