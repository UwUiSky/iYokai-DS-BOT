"""
tests/test_automod_regole_logic.py
==================================
Regole AutoMod (D63): lettura e scrittura del JSON, tetti, chiavi sconosciute, condizioni, ordine delle azioni.
Funzioni coperte: SPEC §6 (AMD-029, 032-040, 042-056, 058-061)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core import automod_regole_logic as L

UTC = timezone.utc


def ctx(**kw):
    base = dict(evento="messaggio", autore_id=1, canale_id=10)
    base.update(kw)
    return L.Contesto(**base)


def cond(**kw):
    return L.condizioni_da_json(kw)


def test_condizioni_vuote_valgono_per_una_persona():
    assert L.condizioni_ok(cond(), ctx())


def test_chiave_sconosciuta_rifiutata():
    with pytest.raises(L.RegolaNonValida):
        cond(boh=1)
    with pytest.raises(L.RegolaNonValida):
        L.azione_da_json({"t": "timeout", "secondi": 5, "x": 1})


def test_il_bot_non_giudica_mai_se_stesso():
    assert not L.condizioni_ok(cond(autori=["persone", "bot", "webhook"]), ctx(e_proprio=True, e_bot=True))


def test_autori_persone_bot_webhook():
    assert not L.condizioni_ok(cond(), ctx(e_bot=True))
    assert L.condizioni_ok(cond(autori=["bot"]), ctx(e_bot=True))
    assert not L.condizioni_ok(cond(autori=["bot"]), ctx(e_webhook=True, e_bot=True))
    assert L.condizioni_ok(cond(autori=["webhook"]), ctx(e_webhook=True, e_bot=True))


def test_canali_e_categorie():
    assert L.condizioni_ok(cond(canali_inclusi=[10]), ctx())
    assert L.condizioni_ok(cond(canali_inclusi=[99]), ctx(categoria_id=99))
    assert not L.condizioni_ok(cond(canali_inclusi=[99]), ctx())
    assert not L.condizioni_ok(cond(canali_esclusi=[99]), ctx(categoria_id=99))
    assert not L.condizioni_ok(cond(canali_esclusi=[10]), ctx())
    assert L.condizioni_ok(cond(canali_inclusi=[7]), ctx(canale_id=11, thread_padre_id=7, in_thread=True))


def test_thread_anche_no_solo():
    assert not L.condizioni_ok(cond(thread="no"), ctx(in_thread=True))
    assert L.condizioni_ok(cond(thread="no"), ctx())
    assert L.condizioni_ok(cond(thread="solo"), ctx(in_thread=True))
    assert not L.condizioni_ok(cond(thread="solo"), ctx())


def test_ruoli():
    r = frozenset({1, 2})
    assert L.condizioni_ok(cond(ruoli_inclusi=[2, 5]), ctx(ruoli_ids=r))
    assert not L.condizioni_ok(cond(ruoli_inclusi=[2, 5], ruoli_modo="tutti"), ctx(ruoli_ids=r))
    assert L.condizioni_ok(cond(ruoli_inclusi=[1, 2], ruoli_modo="tutti"), ctx(ruoli_ids=r))
    assert not L.condizioni_ok(cond(ruoli_esclusi=[1]), ctx(ruoli_ids=r))
    assert not L.condizioni_ok(cond(senza_ruoli=True), ctx(ruoli_ids=r))
    assert L.condizioni_ok(cond(senza_ruoli=True), ctx())
    assert not L.condizioni_ok(cond(utenti_esclusi=[1]), ctx())


def test_eta_account_e_permanenza_nel_dubbio_non_si_punisce():
    assert L.condizioni_ok(cond(eta_account_giorni={"max": 7}), ctx(eta_account_giorni=3))
    assert not L.condizioni_ok(cond(eta_account_giorni={"max": 7}), ctx(eta_account_giorni=30))
    assert not L.condizioni_ok(cond(eta_account_giorni={"min": 30}), ctx(eta_account_giorni=3))
    assert not L.condizioni_ok(cond(nel_server_giorni={"max": 3}), ctx())  # data d'ingresso ignota
    assert L.condizioni_ok(cond(nel_server_giorni={"max": 3}), ctx(nel_server_giorni=1))
    assert not L.condizioni_ok(cond(livello={"max": 5}), ctx(livello=9))


def test_orari_a_cavallo_della_mezzanotte_e_giorni():
    notte = cond(orari={"fuso": "UTC", "dalle": "23:00", "alle": "08:00"})
    assert L.condizioni_ok(notte, ctx(ora=datetime(2026, 11, 2, 23, 30, tzinfo=UTC)))
    assert L.condizioni_ok(notte, ctx(ora=datetime(2026, 11, 3, 7, 0, tzinfo=UTC)))
    assert not L.condizioni_ok(notte, ctx(ora=datetime(2026, 11, 3, 12, 0, tzinfo=UTC)))
    assert not L.condizioni_ok(notte, ctx())  # ora sconosciuta
    lunedi = cond(orari={"fuso": "UTC", "dalle": "00:00", "alle": "23:59", "giorni": [1]})  # 2 nov 2026 = lunedi
    assert L.condizioni_ok(lunedi, ctx(ora=datetime(2026, 11, 2, 10, 0, tzinfo=UTC)))
    assert not L.condizioni_ok(lunedi, ctx(ora=datetime(2026, 11, 3, 10, 0, tzinfo=UTC)))
    # lunedi 23:00-08:00: martedi alle 03:00 appartiene alla notte di lunedi
    assert L.condizioni_ok(
        cond(orari={"fuso": "UTC", "dalle": "23:00", "alle": "08:00", "giorni": [1]}),
        ctx(ora=datetime(2026, 11, 3, 3, 0, tzinfo=UTC)),
    )


@pytest.mark.parametrize("campo", ["canali_inclusi", "canali_esclusi", "ruoli_inclusi", "ruoli_esclusi", "utenti_esclusi"])
def test_tetto_25_id(campo):
    cond(**{campo: list(range(1, 26))})
    with pytest.raises(L.RegolaNonValida):
        cond(**{campo: list(range(1, 27))})


def test_condizioni_giro_completo():
    c = cond(canali_inclusi=[1], ruoli_modo="tutti", eta_account_giorni={"max": 7},
             orari={"fuso": "Europe/Rome", "dalle": "23:00", "alle": "08:00", "giorni": [1, 5]}, autori=["bot"])
    assert L.condizioni_da_json(L.condizioni_a_json(c)) == c
    assert L.condizioni_a_json(L.Condizioni()) == {"v": 1}


def test_orari_fuso_sconosciuto_e_formato():
    with pytest.raises(L.RegolaNonValida):
        cond(orari={"fuso": "Marte/Olimpo"})
    with pytest.raises(L.RegolaNonValida):
        cond(orari={"dalle": "tardi"})


@pytest.mark.parametrize("azione", [
    {"t": "timeout", "secondi": 0}, {"t": "timeout", "secondi": 2_419_201},
    {"t": "cancella_ultimi", "n": 51}, {"t": "cancella_ultimi", "minuti": 61},
    {"t": "ban_tempo", "giorni": 366}, {"t": "slowmode", "secondi": 21_601},
    {"t": "slowmode", "secondi": 5, "durata_s": 86_401}, {"t": "nickname", "testo": "x" * 33},
    {"t": "thread_apri", "nome": "x" * 101}, {"t": "avviso_canale", "testo": "x" * 301},
    {"t": "avviso_canale", "testo": "ciao", "dopo_s": 61}, {"t": "dm", "testo": "x" * 1001},
    {"t": "dm_staff", "utenti": [1, 2, 3, 4, 5, 6]}, {"t": "dm_staff", "utenti": []},
    {"t": "permessi", "canali": [1, 2, 3, 4, 5, 6], "durata_s": 60}, {"t": "permessi"},
    {"t": "permessi", "modello": "dai_admin", "durata_s": 60}, {"t": "inventata"},
    {"t": "ruolo", "ruolo_id": 1, "op": "ruba"},
])
def test_azioni_fuori_tetto_rifiutate(azione):
    with pytest.raises(L.RegolaNonValida):
        L.azione_da_json(azione)


def test_i_segnaposto_contano_nel_tetto():
    # {utente} vale fino a 37 caratteri: 10 volte supera 300
    with pytest.raises(L.RegolaNonValida):
        L.azione_da_json({"t": "avviso_canale", "testo": "{utente}" * 9})
    L.azione_da_json({"t": "avviso_canale", "testo": "{utente} no"})
    assert L.espandi_segnaposto("ciao {utente}", {"utente": "Ann"}) == "ciao Ann"


def test_nickname_vuoto_vuol_dire_pulisci():
    assert L.azione_da_json({"t": "nickname", "testo": ""}).get("testo") == ""


def test_otto_azioni_si_nove_no():
    otto = [{"t": "cancella"}] * 8
    assert len(L.azioni_da_json(otto)) == 8
    with pytest.raises(L.RegolaNonValida):
        L.azioni_da_json(otto + [{"t": "cancella"}])


def test_ordine_delle_azioni_fisso():
    scritte = [{"t": t} if t not in ("timeout", "avviso_canale", "dm_staff") else
               ({"t": "timeout", "secondi": 60} if t == "timeout" else
                {"t": "avviso_canale", "testo": "x"} if t == "avviso_canale" else {"t": "dm_staff", "utenti": [1]})
               for t in ("log", "avviso_canale", "timeout", "dm", "ban", "cancella", "dm_staff", "azzera")]
    ordine = [a.t for a in L.ordina_azioni(L.azioni_da_json(scritte))]
    assert ordine == ["cancella", "dm", "timeout", "ban", "avviso_canale", "log", "dm_staff", "azzera"]
    assert ordine.index("dm") < ordine.index("ban")  # il DM parte prima di kick e ban


def test_contatore_tetti():
    ok = {"nome": "link", "scadenza_giorni": 7, "soglie": [{"violazioni": 3, "minuti": 10, "azioni": [{"t": "timeout", "secondi": 600}]}]}
    c = L.contatore_da_json(ok)
    assert L.contatore_a_json(c) == ok
    with pytest.raises(L.RegolaNonValida):
        L.contatore_da_json({**ok, "soglie": ok["soglie"] * 4})
    with pytest.raises(L.RegolaNonValida):
        L.contatore_da_json({**ok, "scadenza_giorni": 366})
    with pytest.raises(L.RegolaNonValida):
        L.contatore_da_json({**ok, "nome": "x" * 33})


def test_regex_solo_re2_e_tetti():
    L.innesco_da_json({"tipo": "regex", "regex": ["a+b"] * 10})
    with pytest.raises(L.RegolaNonValida):
        L.innesco_da_json({"tipo": "regex", "regex": ["a"] * 11})
    with pytest.raises(L.RegolaNonValida):
        L.innesco_da_json({"tipo": "regex", "regex": ["x" * 261]})
    with pytest.raises(L.RegolaNonValida):
        L.innesco_da_json({"tipo": "regex", "regex": [r"(a)\1"]})  # backreference: non esiste in RE2


def test_regola_giro_completo_e_chiavi():
    r = L.regola_da_json({
        "chiave": "p:3", "tipo": "personale", "nome": "Niente YT", "evento": "messaggio", "gruppo": "raid", "calore": 40,
        "innesco": {"tipo": "regex", "regex": ["foo"]}, "condizioni": {"v": 1, "senza_ruoli": True},
        "azioni": [{"t": "cancella"}, {"t": "timeout", "secondi": 60}],
    })
    assert L.regola_da_json(L.regola_a_json(r)) == r
    with pytest.raises(L.RegolaNonValida):
        L.regola_da_json({"chiave": "boh", "tipo": "personale", "nome": "x"})
    with pytest.raises(L.RegolaNonValida):
        L.regola_da_json({"chiave": "anti_link", "tipo": "filtro", "nome": "x", "calore": 101})
    with pytest.raises(L.RegolaNonValida):
        L.regola_da_json({"chiave": "anti_link", "tipo": "filtro", "nome": "x" * 33})


def test_azioni_dai_nomi_vecchi():
    a = L.azioni_dai_nomi_vecchi(("ban", "mute", "delete", "warn"), 600)
    assert [x.t for x in a] == ["cancella", "warn", "timeout", "ban"]
    assert a[2].get("secondi") == 600
