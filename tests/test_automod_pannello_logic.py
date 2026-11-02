"""
tests/test_automod_pannello_logic.py
====================================
Logica pura del pannello delle regole: categorie, testi delle finestre, menu delle azioni, permessi, embed.
Funzioni coperte: SPEC §6 (AMD-029..056, AMD-067), D63
"""

import pytest

from core import automod_pannello_logic as P
from core.automod_regole_logic import Condizioni, Contatore, Regola, RegolaNonValida, Soglia, azione_da_json, azioni_da_json


def test_ogni_filtro_di_oggi_ha_una_categoria_e_nessuno_e_doppio():
    chiavi = [k for ks in P.FILTRI_PER_CATEGORIA.values() for k in ks]
    assert len(chiavi) == len(set(chiavi))
    assert all(len(ks) <= 8 for ks in P.FILTRI_PER_CATEGORIA.values())  # un menu per categoria, mai oltre 25
    from cogs.automod.automod import _VIOLATION_LABELS

    mancanti = set(_VIOLATION_LABELS) - set(chiavi)
    assert mancanti <= {"parole_sospette"}


def test_categoria_delle_regole_personali_segue_l_evento():
    mk = lambda ev: Regola(chiave="p:1", tipo="personale", nome="x", evento=ev)
    assert P.categoria_di_regola(mk("nome")) == "nomi"
    assert P.categoria_di_regola(mk("thread")) == "vocali"
    assert P.categoria_di_regola(mk("ingresso")) == "eventi"
    assert P.categoria_di_regola(mk("messaggio")) == "personali"
    assert P.categoria_di_regola(Regola(chiave="anti_link", tipo="filtro", nome="x")) == "link"


def test_pagine_da_25():
    voci = list(range(60))
    assert P.pagina_di(voci, 0) == (voci[:25], 3)
    assert P.pagina_di(voci, 2)[0] == voci[50:]
    assert P.pagina_di(voci, 99)[0] == voci[50:]  # fuori misura: ultima
    assert P.pagina_di([], 0) == ([], 1)


@pytest.mark.parametrize("testo,atteso", [("", (None, None)), ("3-7", (3, 7)), ("-7", (None, 7)), ("3-", (3, None)), ("5", (5, 5)), (" 2 - 4 ", (2, 4))])
def test_intervalli(testo, atteso):
    assert P.leggi_intervallo(testo) == atteso


@pytest.mark.parametrize("testo", ["7-3", "a-b", "1-2-3", "99999-"])
def test_intervalli_sbagliati(testo):
    with pytest.raises(RegolaNonValida):
        P.leggi_intervallo(testo)


def test_orario_e_giorni():
    o = P.leggi_orario("23:00-08:00", "1,5")
    assert (o.dalle, o.alle, o.giorni) == ("23:00", "08:00", (1, 5))
    assert P.leggi_orario("", "1") is None
    assert P.leggi_orario("9:00-17:30", "").giorni == tuple(range(1, 8))
    for brutto in (("tardi", ""), ("23:00-08:00", "8"), ("23:00-08:00", "x")):
        with pytest.raises(RegolaNonValida):
            P.leggi_orario(*brutto)


def test_durate_e_id():
    assert P.leggi_durata("10m") == 600 and P.leggi_durata("") is None
    with pytest.raises(RegolaNonValida):
        P.leggi_durata("40d", massimo=2_419_200)
    assert P.leggi_id("<@&123456789012345678>") == 123456789012345678
    assert P.leggi_id("") is None
    with pytest.raises(RegolaNonValida):
        P.leggi_id("ciao")
    assert P.leggi_ids("123456789012345678 <@123456789012345679>,123456789012345678", 5) == [123456789012345678, 123456789012345679]
    with pytest.raises(RegolaNonValida):
        P.leggi_ids(" ".join(str(10**15 + i) for i in range(6)), 5)


def test_azione_del_contatore_scritta_a_mano():
    assert P.leggi_azione_soglia("timeout 1h").get("secondi") == 3600
    assert P.leggi_azione_soglia("ban_tempo 3").get("giorni") == 3
    assert P.leggi_azione_soglia("kick").t == "kick"
    with pytest.raises(RegolaNonValida):
        P.leggi_azione_soglia("vola")


def test_menu_azioni_tiene_i_parametri_e_toglie_le_deselezionate():
    base = azioni_da_json([{"t": "timeout", "secondi": 900}, {"t": "log"}, {"t": "kick"}])
    nuove = P.imposta_azioni(base, {"timeout", "cancella", "ban_tempo"}, P.AZIONI_UTENTE_MENU)
    d = {a.t: a for a in nuove}
    assert d["timeout"].get("secondi") == 900  # parametro scelto a mano: resta
    assert d["ban_tempo"].get("giorni") == 7  # nuova: parametri di base
    assert "kick" not in d  # deselezionata
    assert "log" in d  # fuori dal gruppo di questo menu: non si tocca
    assert "ruolo" not in d  # richiede una scelta: solo dalla finestra


def test_ogni_azione_dei_menu_si_costruisce_con_i_parametri_di_base():
    for t in (*P.AZIONI_UTENTE_MENU, *P.AZIONI_CANALE_STAFF_MENU):
        if t in P.SOLO_DA_FINESTRA:
            continue
        if t in ("dm_staff", "decide_staff", "azzera"):
            continue
        azione_da_json({"t": t, **P.PARAMETRI_BASE.get(t, {})})


def test_menu_hanno_meno_di_25_voci():
    assert len(P.AZIONI_UTENTE_MENU) <= 25 and len(P.AZIONI_CANALE_STAFF_MENU) <= 25


def test_permessi_mancanti():
    class Perm:
        moderate_members = True
        ban_members = False
        manage_messages = True
        administrator = False

    az = azioni_da_json([{"t": "timeout", "secondi": 60}, {"t": "ban"}, {"t": "ban_tempo", "giorni": 1}, {"t": "cancella"}])
    assert P.permessi_mancanti(az, Perm) == ["ban_members"]
    Perm.administrator = True
    assert P.permessi_mancanti(az, Perm) == []


def test_embed_nel_caso_peggiore_resta_entro_i_limiti():
    cond = Condizioni(canali_inclusi=tuple(range(10**17, 10**17 + 25)), canali_esclusi=tuple(range(10**17, 10**17 + 25)),
                      ruoli_inclusi=tuple(range(10**17, 10**17 + 25)), ruoli_esclusi=tuple(range(10**17, 10**17 + 25)),
                      utenti_esclusi=tuple(range(10**17, 10**17 + 25)))
    az = azioni_da_json([{"t": "avviso_canale", "testo": "x" * 300}] * 8)
    ct = Contatore("n" * 32, 30, tuple(Soglia(3, 10, az[:2]) for _ in range(3)))
    r = Regola(chiave="p:1", tipo="personale", nome="n" * 32, condizioni=cond, azioni=az, contatore=ct, gruppo="g" * 32,
               innesco={"tipo": "regex", "regex": ["a" * 260] * 10})
    campi = P.campi_embed(r)
    assert all(len(v) <= 1024 for _, v in campi)
    assert sum(len(n) + len(v) for n, v in campi) < 6000
