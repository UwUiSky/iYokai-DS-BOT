"""
tests/test_aggiorna_vpn.py
==========================
D64: lo script che scarica gli elenchi VPN/Tor/ASN. Solo https, un file rotto o troppo piccolo non
sostituisce quello buono, nessun file a metà, intestazione con fonte e licenza, e il file dei fusi.
"""

import io
import os
from datetime import date

import pytest

from core import verify_vpn_logic as logica
from scripts import aggiorna_vpn as script

OGGI = date(2026, 11, 1)


class _Risposta(io.BytesIO):
    url = "https://example.com/x"  # dove si arriva dopo i reindirizzamenti

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *errore):
        self.close()


def _finto(monkeypatch, contenuti):
    chiamati = []

    def urlopen(indirizzo, timeout):
        chiamati.append(indirizzo)
        c = contenuti[indirizzo] if isinstance(contenuti, dict) else contenuti
        if isinstance(c, Exception):
            raise c
        return _Risposta(c)

    monkeypatch.setattr(script.urllib.request, "urlopen", urlopen)
    return chiamati


def _fonte(nome):
    return next(f for f in script.FONTI if f.file == nome)


def test_tutte_le_fonti_sono_https_e_dichiarano_la_licenza():
    assert {f.file for f in script.FONTI} == {
        "asn_hosting.txt", "tor_uscita.txt", "reti_vpn.txt", "reti_datacenter.txt"}
    for f in script.FONTI:
        assert f.licenza and f.descrizione and f.indirizzi and all(i.startswith("https://") for i in f.indirizzi)


def test_scarica_scrive_il_file_con_intestazione_e_si_rilegge(monkeypatch, tmp_path):
    reti = "".join(f"10.{n}.0.0/16\n" for n in range(150)).encode()
    _finto(monkeypatch, reti)
    assert script.aggiorna(_fonte("reti_vpn.txt"), str(tmp_path), OGGI) == 150  # IPv4 e IPv6 vanno in coda: stesse 150 reti
    testo = (tmp_path / "reti_vpn.txt").read_text()
    assert testo.startswith("# reti di VPN note") and "Licenza: MIT" in testo and "2026-11-01" in testo
    assert len(logica.ElencoReti.da_testo(testo)) == 150  # l'intestazione non rompe la lettura
    assert [p.name for p in tmp_path.iterdir()] == ["reti_vpn.txt"]


def test_asn_con_intestazione_si_rilegge(monkeypatch, tmp_path):
    csv = "ASN,Entity\n" + "".join(f'{n},"Host {n}, Inc."\n' for n in range(1000, 1200))
    _finto(monkeypatch, csv.encode())
    assert script.aggiorna(_fonte("asn_hosting.txt"), str(tmp_path), OGGI) == 200
    assert len(logica.leggi_asn((tmp_path / "asn_hosting.txt").read_text())) == 200


@pytest.mark.parametrize("contenuto", [
    b"<html>404 Not Found</html>", b"", b"1.2.3.4\n", b"\xff\xfe\x00\x01", "x".encode() * 100,
])
def test_un_file_rotto_o_troppo_piccolo_non_sostituisce_quello_buono(monkeypatch, tmp_path, contenuto):
    buono = tmp_path / "tor_uscita.txt"
    buono.write_text("il file buono di prima\n")
    _finto(monkeypatch, contenuto)
    with pytest.raises((ValueError, UnicodeDecodeError)):
        script.aggiorna(_fonte("tor_uscita.txt"), str(tmp_path), OGGI)
    assert buono.read_text() == "il file buono di prima\n"
    assert [p.name for p in tmp_path.iterdir()] == ["tor_uscita.txt"]  # nessun resto a metà


def test_errore_di_rete_lascia_il_file_di_prima(monkeypatch, tmp_path):
    (tmp_path / "tor_uscita.txt").write_text("buono\n")
    _finto(monkeypatch, script.urllib.error.URLError("giù"))
    with pytest.raises(script.urllib.error.URLError):
        script.aggiorna(_fonte("tor_uscita.txt"), str(tmp_path), OGGI)
    assert (tmp_path / "tor_uscita.txt").read_text() == "buono\n"


def test_file_enorme_rifiutato(monkeypatch, tmp_path):
    monkeypatch.setattr(script, "TETTO_BYTE", 100)
    _finto(monkeypatch, b"1.2.3.4\n" * 50)
    with pytest.raises(ValueError):
        script.aggiorna(_fonte("tor_uscita.txt"), str(tmp_path), OGGI)


def test_indirizzo_non_https_rifiutato():
    with pytest.raises(ValueError):
        script._scarica_testo("http://example.com/x")


def test_fusi_generati_dal_file_dei_fusi_e_quello_del_repo_e_valido(tmp_path):
    zone_tab = tmp_path / "zone.tab"
    zone_tab.write_text("# c\nIT\t+4154+01229\tEurope/Rome\nCH\t+4723+00832\tEurope/Zurich\nLI\t+4709+00931\tEurope/Zurich\n")
    assert script.genera_fusi(str(tmp_path / "out"), str(zone_tab)) == 2
    fusi = logica.leggi_fusi((tmp_path / "out" / "fuso_paesi.txt").read_text())
    assert fusi == {"Europe/Rome": frozenset({"IT"}), "Europe/Zurich": frozenset({"CH", "LI"})}
    nel_repo = logica.leggi_fusi(open(os.path.join("data", "vpn", "fuso_paesi.txt"), encoding="utf-8").read())
    assert len(nel_repo) > 300 and nel_repo["Europe/Rome"] == frozenset({"IT"})
    assert not logica.fuso_incoerente("Europe/Rome", "IT", nel_repo)
    assert logica.fuso_incoerente("America/New_York", "IT", nel_repo)


def test_reindirizzamento_verso_http_rifiutato(monkeypatch, tmp_path):
    """urllib segue anche un reindirizzamento da https a http: il file arrivato così non si usa."""
    (tmp_path / "tor_uscita.txt").write_text("buono\n")
    monkeypatch.setattr(_Risposta, "url", "http://example.com/x")
    _finto(monkeypatch, "".join(f"1.2.3.{n}\n" for n in range(200)).encode())
    with pytest.raises(ValueError):
        script.aggiorna(_fonte("tor_uscita.txt"), str(tmp_path), OGGI)
    assert (tmp_path / "tor_uscita.txt").read_text() == "buono\n"
