"""
tests/test_immagini_azione_logic.py
===================================
Cosa si fa dopo l'esito del filtro immagini (D62).
"""

import pytest

from core import immagini_azione_logic as az
from core import immagini_pipeline as pl
from core.immagini_opzioni import OpzioniImmagini


def opz(azione="cancella", minuti=10):
    return OpzioniImmagini(True, azione, minuti, None)


def e(verdetto="malevola", **kw):
    return pl.EsitoImmagine(verdetto, "ab", ("x",), **kw)


def test_pulita_non_fa_nulla():
    assert az.decidi(e("pulita"), opz(), a_rischio=True) == az.Decisione()


def test_cancella_con_dm_e_log():
    d = az.decidi(e("sospetta"), opz("cancella"), a_rischio=False)
    assert d == az.Decisione(cancella=True, dm=az.DM_RIMOSSA, log=True)


def test_azione_timeout():
    d = az.decidi(e("sospetta"), opz("timeout", 45), a_rischio=False)
    assert d.cancella and d.timeout_minuti == 45 and d.dm == az.DM_TIMEOUT and d.log


def test_malevola_mette_sempre_in_timeout_anche_con_cancella():
    d = az.decidi(e("malevola"), opz("cancella", 20), a_rischio=False)
    assert d.cancella and d.timeout_minuti == 20 and d.dm == az.DM_TIMEOUT


def test_sospetta_non_mette_in_timeout():
    assert az.decidi(e("sospetta"), opz("cancella"), a_rischio=False).timeout_minuti is None


def test_avvisa_lascia_il_messaggio_ma_non_per_la_malevola():
    d = az.decidi(e("sospetta"), opz("avvisa"), a_rischio=False)
    assert d == az.Decisione(avvisa_nel_canale=True, log=True)
    d = az.decidi(e("malevola"), opz("avvisa"), a_rischio=False)
    assert d.cancella and d.timeout_minuti == 10


def test_simile_solo_log():
    assert az.decidi(e("sospetta", solo_avviso=True), opz("timeout"), a_rischio=True) == az.Decisione(log=True)


def test_coda_piena_account_normale_il_messaggio_resta():
    d = az.decidi(pl.EsitoImmagine(non_analizzata=pl.NON_ANALIZZATA_CODA), opz(), a_rischio=False)
    assert not d.cancella and d.log and d.avvisa_owner


def test_coda_piena_account_nuovo_riprova_fra_poco():
    d = az.decidi(pl.EsitoImmagine(non_analizzata=pl.NON_ANALIZZATA_CODA), opz(), a_rischio=True)
    assert d.cancella and d.dm == az.DM_RIPROVA and d.avvisa_owner


def test_sandbox_ferma_non_avvisa_l_owner_della_coda():
    d = az.decidi(pl.EsitoImmagine(non_analizzata=pl.NON_ANALIZZATA_SANDBOX), opz(), a_rischio=False)
    assert d.log and not d.avvisa_owner


def test_troppo_grande_non_fa_rumore():
    assert az.decidi(pl.EsitoImmagine(non_analizzata=pl.NON_ANALIZZATA_GRANDE), opz(), a_rischio=True) == az.Decisione()


@pytest.mark.parametrize("account,server,atteso", [(3, 100, True), (30, 0.5, True), (30, 5, False), (30, None, False), (7, 1, False)])
def test_autore_a_rischio(account, server, atteso):
    assert az.autore_a_rischio(account, server) is atteso
