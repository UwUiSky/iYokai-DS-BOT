"""
tests/test_verify_vpn_logica.py
===============================
D64: gli strati di rilevazione VPN/proxy nella verifica web, con dati finti (nessun file vero,
nessuna rete): reti IPv4 e IPv6, ASN, nodi Tor, intestazioni di proxy (fidato o no), fuso orario,
IP privati mai bloccati e regola «un segnale forte blocca, uno debole da solo no».
"""

import pytest

from core import verify_vpn_logic as logica


# ------------------------------------------------------------- IP controllabili
@pytest.mark.parametrize("ip", [
    "10.0.0.1", "192.168.1.5", "127.0.0.1", "169.254.1.1", "100.64.0.9", "203.0.113.7", "::1", "fe80::1",
    "fc00::1", "2001:db8::1", "::ffff:10.0.0.1", "0.0.0.0", "224.0.0.1", "?", "", "non-un-ip", "300.1.1.1",
])
def test_ip_privati_locali_o_storti_non_si_controllano_mai(ip):
    assert logica.ip_controllabile(ip) is None


def test_ip_pubblici_si_controllano_anche_ipv6_e_mappati():
    assert str(logica.ip_controllabile("8.8.8.8")) == "8.8.8.8"
    assert str(logica.ip_controllabile("2606:4700:4700::1111")) == "2606:4700:4700::1111"
    assert str(logica.ip_controllabile("::ffff:8.8.8.8")) == "8.8.8.8"  # IPv4 dentro IPv6: stesso indirizzo
    assert logica.ip_controllabile(None) is None


# ------------------------------------------------------------------ elenco reti
def test_elenco_reti_ipv4_e_ipv6():
    elenco = logica.ElencoReti.da_testo(
        "# fonte finta\n1.2.3.0/24\n9.9.9.9\n2001:abcd::/32\n\nnon-una-rete\n2001:ffff:1::5/128\n; altro commento\n"
    )
    assert len(elenco) == 4  # le righe storte e i commenti si ignorano
    assert logica.ip_controllabile("1.2.3.77") is not None
    assert elenco.contiene(logica.ip_controllabile("1.2.3.77"))
    assert not elenco.contiene(logica.ip_controllabile("1.2.4.1"))
    assert elenco.contiene(logica.ip_controllabile("9.9.9.9"))  # un indirizzo solo vale /32
    assert elenco.contiene(logica.ip_controllabile("2001:abcd:1234::1"))
    assert not elenco.contiene(logica.ip_controllabile("2001:abce::1"))
    assert elenco.contiene(logica.ip_controllabile("2001:ffff:1::5"))
    assert not elenco.contiene(logica.ip_controllabile("2001:ffff:1::6"))
    assert not logica.ElencoReti.da_testo("").contiene(logica.ip_controllabile("8.8.8.8"))


def test_elenco_reti_non_confonde_v4_e_v6_e_tiene_la_rete_piu_larga():
    elenco = logica.ElencoReti.da_testo("0.0.0.0/8\n::/16\n8.0.0.0/8\n8.8.0.0/16")
    assert elenco.contiene(logica.ip_controllabile("8.8.8.8"))
    assert not elenco.contiene(logica.ip_controllabile("2606::1"))


# --------------------------------------------------------------------- ASN, Tor
def test_elenco_asn_da_csv_e_da_righe_semplici():
    asn = logica.leggi_asn('ASN,Entity\n1442,"Surehosting, Inc."\n3223,"Voxility"\n# x\nAS64500\n 64501 \nciao\n-5\n')
    assert asn == frozenset({1442, 3223, 64500, 64501})
    assert logica.leggi_asn("") == frozenset()


def test_asn_dal_record_della_banca_dati():
    assert logica.asn_da_record({"autonomous_system_number": 15169, "autonomous_system_organization": "G"}) == 15169
    assert logica.asn_da_record({"autonomous_system_number": "15169"}) is None  # solo numeri veri
    assert logica.asn_da_record({"autonomous_system_number": -1}) is None
    assert logica.asn_da_record({}) is None and logica.asn_da_record(None) is None


def test_nodi_tor_normalizzati_ipv4_e_ipv6():
    tor = logica.leggi_nodi_tor("1.2.3.4\n# c\n2001:DB8::0001\n  5.6.7.8  \nnon-ip\n")
    assert tor == frozenset({"1.2.3.4", "5.6.7.8", "2001:db8::1"})
    assert logica.ip_in_nodi_tor(logica.ip_controllabile("2606:4700:4700::1111"), frozenset({"2606:4700:4700::1111"}))
    assert logica.ip_in_nodi_tor(logica.ip_controllabile("::ffff:1.2.3.4"), tor)


# ------------------------------------------------------- intestazioni di proxy
def test_intestazioni_di_proxy_da_client_pubblico_non_fidato():
    h = {"X-Forwarded-For": "1.1.1.1"}
    assert logica.segnali_intestazioni("8.8.8.8", h, frozenset()) == (logica.METODO_INTESTAZIONI,)
    assert logica.segnali_intestazioni("8.8.8.8", {"Forwarded": "for=1.1.1.1"}, frozenset()) == (logica.METODO_INTESTAZIONI,)
    assert logica.segnali_intestazioni("8.8.8.8", {"via": "1.1 squid"}, frozenset()) == (logica.METODO_VIA,)
    assert logica.segnali_intestazioni("8.8.8.8", {"Via": "1.1 x", "X-Forwarded-For": "2.2.2.2"}, frozenset()) == (
        logica.METODO_INTESTAZIONI, logica.METODO_VIA)
    assert logica.segnali_intestazioni("8.8.8.8", {"Accept": "text/html"}, frozenset()) == ()
    assert logica.segnali_intestazioni("8.8.8.8", {"X-Forwarded-For": "  "}, frozenset()) == ()  # vuota


def test_dal_proxy_fidato_o_da_rete_locale_le_intestazioni_non_contano():
    h = {"X-Forwarded-For": "1.1.1.1", "Via": "1.1 nginx"}
    assert logica.segnali_intestazioni("8.8.8.8", h, frozenset({"8.8.8.8"})) == ()  # le scrive il nostro proxy
    # reverse proxy locale non dichiarato tra i fidati: bloccherebbe tutti, quindi niente segnale
    assert logica.segnali_intestazioni("127.0.0.1", h, frozenset()) == ()
    assert logica.segnali_intestazioni("10.1.2.3", h, frozenset()) == ()
    assert logica.segnali_intestazioni("::1", h, frozenset()) == ()
    assert logica.segnali_intestazioni(None, h, frozenset()) == ()
    assert logica.segnali_intestazioni("2606:4700::1", h, frozenset()) == (
        logica.METODO_INTESTAZIONI, logica.METODO_VIA)  # IPv6 pubblico non fidato


# ------------------------------------------------------------------ fuso orario
FUSI = logica.leggi_fusi("# x\nEurope/Rome\tIT\nEurope/Zurich\tCH,LI\nAmerica/New_York\tUS\nAsia/Kolkata\tIN\n\nstorta\n")


def test_fusi_letti_dal_file():
    assert FUSI["Europe/Zurich"] == frozenset({"CH", "LI"})
    assert "storta" not in FUSI and len(FUSI) == 4


def test_fuso_diverso_dal_paese_dell_ip_e_un_segnale():
    assert logica.fuso_incoerente("America/New_York", "IT", FUSI)
    assert not logica.fuso_incoerente("Europe/Rome", "IT", FUSI)
    assert not logica.fuso_incoerente("Europe/Zurich", "LI", FUSI)
    assert not logica.fuso_incoerente("Europe/Zurich", "CH", FUSI)


@pytest.mark.parametrize("fuso, paese", [
    (None, "IT"), ("", "IT"), ("Europe/Rome", None), ("UTC", "IT"), ("Etc/GMT+3", "IT"), ("Mars/Olympus", "IT"),
    ("x" * 200, "IT"), ("Europe/Rome\n<script>", "IT"),
])
def test_fuso_ignoto_o_storto_o_paese_ignoto_non_da_segnale(fuso, paese):
    assert not logica.fuso_incoerente(fuso, paese, FUSI)


def test_fuso_valido_solo_nomi_tz():
    assert logica.fuso_pulito("Europe/Rome") == "Europe/Rome"
    assert logica.fuso_pulito("America/Argentina/Buenos_Aires") == "America/Argentina/Buenos_Aires"
    assert logica.fuso_pulito("<b>") is None and logica.fuso_pulito("") is None and logica.fuso_pulito(5) is None
    assert logica.fuso_pulito("A" * 65) is None


# ------------------------------------------------------------------- decisione
def test_un_segnale_forte_blocca_subito_uno_debole_da_solo_no():
    for forte in (logica.METODO_ASN, logica.METODO_TOR, logica.METODO_ELENCO, logica.METODO_INTESTAZIONI,
                  logica.METODO_SERVIZIO):
        r = logica.decidi([forte], [])
        assert r.bloccato and r.metodi == (forte,)
    assert not logica.decidi([], [logica.METODO_FUSO]).bloccato
    assert not logica.decidi([], [logica.METODO_VIA]).bloccato
    assert not logica.decidi([], []).bloccato


def test_due_segnali_deboli_insieme_bloccano():
    r = logica.decidi([], [logica.METODO_FUSO, logica.METODO_VIA])
    assert r.bloccato and r.metodi == (logica.METODO_FUSO, logica.METODO_VIA)
    r = logica.decidi([logica.METODO_TOR, logica.METODO_TOR], [logica.METODO_FUSO])  # niente doppioni
    assert r.metodi == (logica.METODO_TOR, logica.METODO_FUSO)
    assert logica.testo_metodi(r.metodi) == "tor,fuso"


def test_reti_troppo_larghe_negli_elenchi_si_ignorano():
    """Un elenco sbagliato con 0.0.0.0/0 o ::/0 bloccherebbe tutti: reti più larghe di /8 (IPv4) e /16 (IPv6) no."""
    elenco = logica.ElencoReti.da_testo("0.0.0.0/0\n0.0.0.0/1\n::/0\n2000::/3\n4.0.0.0/8\n2600:1f00::/24\n")
    assert len(elenco) == 2
    assert not elenco.contiene(logica.ip_controllabile("9.9.9.9"))
    assert not elenco.contiene(logica.ip_controllabile("2001:4860:4860::8888"))
    assert elenco.contiene(logica.ip_controllabile("4.1.2.3"))
    assert elenco.contiene(logica.ip_controllabile("2600:1f00::1"))
