"""
tests/test_user_app_messaggi.py
===============================
SPEC B.2 (#107): controllo dei link, citazione come immagine, testi dei menu sul messaggio.
"""

import io

from PIL import Image

from core import user_app_messaggi as m


def test_testo_segnalibro_una_riga_e_tagliato():
    assert m.testo_segnalibro("ciao\n\n  mondo ") == "ciao mondo"
    assert len(m.testo_segnalibro("x" * 900)) == 500
    assert m.testo_segnalibro(None) == ""


def test_controlla_link_distingue_lista_sospetto_accorciatore_e_nessun_segnale():
    lista = frozenset({"truffa-vera.example"})
    esiti = {e.dominio: e.stato for e in m.controlla_link(
        "guarda https://truffa-vera.example/x e https://free-nitro-gift.com e https://bit.ly/abc "
        "e https://discord.com/app e https://rust-lang.org", lista)}
    assert esiti["truffa-vera.example"] == m.STATO_LISTA
    assert esiti["free-nitro-gift.com"] == m.STATO_SOSPETTO
    assert esiti["bit.ly"] == m.STATO_ACCORCIATORE
    assert esiti["discord.com"] == m.STATO_NESSUN_SEGNALE
    assert esiti["rust-lang.org"] == m.STATO_NESSUN_SEGNALE


def test_controlla_link_senza_link_e_con_tetto():
    assert m.controlla_link("nessun link qui", frozenset()) == []
    molti = " ".join(f"https://sito{n}.example.org" for n in range(30))
    assert len(m.controlla_link(molti, frozenset())) == m.MAX_LINK_CONTROLLATI


def test_citazione_e_un_png_valido_con_testo_lungo_e_senza_avatar():
    png = m.citazione_png("parola " * 300, "Anna", None)
    immagine = Image.open(io.BytesIO(png))
    assert immagine.format == "PNG" and immagine.width == 900 and immagine.height < 1000


def test_citazione_usa_un_avatar_vero_e_regge_un_avatar_rotto():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (255, 0, 0)).save(buffer, format="PNG")
    assert Image.open(io.BytesIO(m.citazione_png("ciao", "Anna", buffer.getvalue()))).format == "PNG"
    assert Image.open(io.BytesIO(m.citazione_png("ciao", "Anna", b"non e' un'immagine"))).format == "PNG"


def test_istruzioni_ai_nella_lingua_della_persona():
    assert "inglese (en)" in m.istruzioni_ai("traduci", "en")
    assert "italiano (it)" in m.istruzioni_ai("spiega", "it")


def test_testo_segnalazione_ha_autore_link_e_motivo_tagliati():
    t = m.testo_segnalazione(5, "Mallory", "https://discord.com/channels/1/2/3", "x" * 2000, "truffa")
    assert "ID 5" in t and "channels/1/2/3" in t and "truffa" in t and len(t) < 1200
