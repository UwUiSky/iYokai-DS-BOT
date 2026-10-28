"""
tests/test_user_app_strumenti.py
================================
Strumenti personali di iYokai App (SPEC §B.4): calcolatrice, conversioni, fusi, colori, QR. Logica pura.
"""

from datetime import datetime, timezone

import pytest

from core import user_app_strumenti as s
from core.user_app_strumenti import ErroreStrumento


@pytest.mark.parametrize("espr,atteso", [
    ("2+3*4", "14"), ("(2+3)*4", "20"), ("10/4", "2.5"), ("2^10", "1024"), ("7//2", "3"), ("7%4", "3"),
    ("sqrt(16)", "4"), ("round(2,5)", "2"), ("-3+abs(-5)", "2"), ("1,5*2", "3"), ("pi*2", "6.283185307"),
])
def test_calcola(espr, atteso):
    assert s.calcola(espr) == atteso


@pytest.mark.parametrize("espr,chiave", [
    ("1/0", "app_calc_divisione_zero"), ("9**9**9", "app_calc_troppo_grande"), ("10**1000", "app_calc_troppo_grande"),
    ("__import__('os')", "app_calc_non_valida"), ("a+1", "app_calc_non_valida"), ("", "app_calc_non_valida"),
    ("1+" * 80 + "1", "app_calc_non_valida"), ("sqrt(-1)", "app_calc_non_valida"), ("(1).real", "app_calc_non_valida"),
    ("lambda: 1", "app_calc_non_valida"), ("2**0.5**1000", "app_calc_troppo_grande"),
])
def test_calcola_rifiuta_senza_eseguire_codice(espr, chiave):
    with pytest.raises(ErroreStrumento) as e:
        s.calcola(espr)
    assert e.value.chiave == chiave


def test_conversioni():
    assert s.converti(1, "km", "m") == 1000
    assert round(s.converti(1, "mi", "km"), 3) == 1.609
    assert s.converti(0, "c", "f") == 32 and round(s.converti(100, "c", "k"), 2) == 373.15
    assert round(s.converti(212, "F", "c"), 6) == 100
    assert s.converti(1, "kib", "b") == 1024
    assert round(s.converti(100, "km/h", "mph"), 2) == 62.14


def test_conversioni_errori():
    with pytest.raises(ErroreStrumento) as e:
        s.converti(1, "km", "kg")
    assert e.value.chiave == "app_conv_categorie"
    with pytest.raises(ErroreStrumento) as e:
        s.converti(1, "km", "xx")
    assert e.value.chiave == "app_conv_unita"
    with pytest.raises(ErroreStrumento):
        s.converti(float("inf"), "km", "m")


def test_fusi_orari():
    adesso = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # inverno: Roma UTC+1, New York UTC-5
    da, a = s.converti_ora("18:30", "Europe/Rome", "America/New_York", adesso)
    assert (da.hour, a.hour, a.minute) == (18, 12, 30)
    da, a = s.converti_ora(None, "UTC", "Asia/Tokyo", adesso)
    assert (da.hour, a.hour) == (12, 21)


def test_fusi_errori_e_completamento():
    for cattivo in ("Marte/Olimpo", "../etc/passwd", ""):
        with pytest.raises(ErroreStrumento) as e:
            s.zona(cattivo)
        assert e.value.chiave == "app_fuso_sconosciuto"
    with pytest.raises(ErroreStrumento) as e:
        s.converti_ora("25:99", "UTC", "UTC")
    assert e.value.chiave == "app_fuso_ora"
    proposte = s.zone_che_iniziano("rome")
    assert "Europe/Rome" in proposte and len(s.zone_che_iniziano("")) == 25


def test_colori():
    c = s.leggi_colore("#FF8800")
    assert (c.hex, c.rgb, c.intero) == ("#ff8800", "rgb(255, 136, 0)", 0xFF8800)
    assert c.hsl == "hsl(32, 100%, 50%)"
    assert s.leggi_colore("f80") == s.leggi_colore("rgb(255,136,0)") == s.leggi_colore("255 136 0") == c
    for cattivo in ("rgb(300,0,0)", "zzz", "#12345"):
        with pytest.raises(ErroreStrumento):
            s.leggi_colore(cattivo)
    assert s.immagine_colore(c).startswith(b"\x89PNG")


def test_qr():
    assert s.qr_png("https://iyokai.example/ciao").startswith(b"\x89PNG")
    for cattivo in ("", "x" * 301):
        with pytest.raises(ErroreStrumento) as e:
            s.qr_png(cattivo)
        assert e.value.chiave == "app_qr_testo"
