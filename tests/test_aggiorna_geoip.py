"""
tests/test_aggiorna_geoip.py
============================
D53: lo script che scarica la banca dati dei paesi. Solo https, e un file scaricato
rotto non sostituisce quello buono né lascia file a metà nella cartella.
"""

import gzip
import io

import pytest

from scripts import aggiorna_geoip


class _Risposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *errore):
        self.close()


def test_indirizzo_solo_https():
    assert aggiorna_geoip.INDIRIZZO.startswith("https://download.db-ip.com/")


def test_file_rotto_non_sostituisce_quello_buono_e_non_lascia_resti(monkeypatch, tmp_path):
    destinazione = tmp_path / "paesi.mmdb"
    destinazione.write_bytes(b"il file buono di prima")
    chiamati = []

    def urlopen_finto(indirizzo, timeout):
        chiamati.append(indirizzo)
        return _Risposta(gzip.compress(b"non e' una banca dati MMDB"))

    monkeypatch.setattr(aggiorna_geoip.urllib.request, "urlopen", urlopen_finto)
    with pytest.raises(SystemExit):
        aggiorna_geoip.scarica(str(destinazione))
    assert len(chiamati) == 2  # il file rotto del mese corrente non ferma il tentativo col mese prima
    assert destinazione.read_bytes() == b"il file buono di prima"
    assert [p.name for p in tmp_path.iterdir()] == ["paesi.mmdb"]
