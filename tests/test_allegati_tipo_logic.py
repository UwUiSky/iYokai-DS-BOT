"""
tests/test_allegati_tipo_logic.py
=================================
Tipo vero dai primi byte e decisione unica sugli allegati degli utenti (D74, #160).
"""

import hashlib

import pytest

from core import allegati_tipo_logic as t

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 40
GIF = b"GIF89a" + b"\0" * 40
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\0" * 20
PE = b"MZ\x90\x00" + b"\0" * 60 + b"This program cannot be run in DOS mode"
ELF = b"\x7fELF\x02\x01\x01" + b"\0" * 40
MACHO = b"\xcf\xfa\xed\xfe" + b"\0" * 40
LNK = bytes.fromhex("4C0000000114020000000000C000000000000046") + b"\0" * 20
PDF = b"%PDF-1.7\n1 0 obj\n"
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\0" * 30
OGG = b"OggS\x00\x02" + b"\0" * 30
WAV = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\0" * 20
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
M4A = b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00M4A mp42"
WEBM = b"\x1a\x45\xdf\xa3" + b"\0" * 30
DOCX = b"PK\x03\x04" + b"\0" * 26 + b"[Content_Types].xml" + b"\0" * 20 + b"word/document.xml"
ODT = b"PK\x03\x04" + b"\0" * 26 + b"mimetypeapplication/vnd.oasis.opendocument.text"
ZIP = b"PK\x03\x04" + b"\0" * 26 + b"cartella/file.txt"
OLE = bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 60
RAR = b"Rar!\x1a\x07\x00" + b"\0" * 20
SZ = b"7z\xbc\xaf\x27\x1c" + b"\0" * 20
GZ = b"\x1f\x8b\x08\x00" + b"\0" * 20
SCRIPT = b"#!/bin/sh\nrm -rf /\n"
HTML = b"<!DOCTYPE html><html><script>x</script></html>"
SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'
TESTO = "ciao, questo è un testo\n".encode()
IGNOTO = bytes(range(1, 200))


@pytest.mark.parametrize("dati,categoria", [
    (PNG, "immagine"), (JPEG, "immagine"), (GIF, "immagine"), (WEBP, "immagine"),
    (PE, "eseguibile"), (ELF, "eseguibile"), (MACHO, "eseguibile"), (LNK, "eseguibile"), (SCRIPT, "eseguibile"),
    (PDF, "pdf"), (MP3, "audio"), (OGG, "audio"), (WAV, "audio"), (M4A, "audio"),
    (MP4, "video"), (WEBM, "video"),
    (DOCX, "office"), (ODT, "office"), (OLE, "office"),
    (ZIP, "archivio"), (RAR, "archivio"), (SZ, "archivio"), (GZ, "archivio"),
    (HTML, "web"), (SVG, "web"), (TESTO, "testo"), (IGNOTO, "sconosciuto"), (b"", "sconosciuto"),
])
def test_categoria_dai_byte(dati, categoria):
    assert t.riconosci(dati).categoria == categoria


def test_il_nome_non_cambia_la_categoria():
    assert t.decidi(PE, "foto.png").tipo.categoria == "eseguibile"
    assert t.decidi(PNG, "foto.exe").tipo.categoria == "immagine"


def test_immagine_vera_va_alla_strada_d62():
    d = t.decidi(PNG, "foto.png", "image/png")
    assert (d.azione, d.travestito, d.motivi) == (t.IMMAGINE, False, ())
    assert d.sha256 == hashlib.sha256(PNG).hexdigest() and d.dimensione == len(PNG)


def test_eseguibile_travestito_da_immagine_si_rifiuta():
    d = t.decidi(PE, "foto.png", "image/png")
    assert d.azione == t.RIFIUTA and d.travestito and "tipo_non_coincide" in d.motivi


def test_eseguibile_dichiarato_si_rifiuta_ma_non_e_travestito():
    d = t.decidi(PE, "setup.exe")
    assert d.azione == t.RIFIUTA and not d.travestito and "eseguibile" in d.motivi


@pytest.mark.parametrize("nome", ["foto.png.exe", "relazione.pdf.scr", "a.jpg.bat"])
def test_doppia_estensione(nome):
    d = t.decidi(PE, nome)
    assert d.azione == t.RIFIUTA and d.travestito and "doppia_estensione" in d.motivi


def test_doppia_estensione_con_byte_immagine_si_rifiuta():
    d = t.decidi(PNG, "foto.png.exe")
    assert d.azione == t.RIFIUTA and "doppia_estensione" in d.motivi


@pytest.mark.parametrize("nome", ["foto\u202egpj.exe", "doc\u202etxt.png", "a\u2066b.png"])
def test_inversione_del_testo_nel_nome(nome):
    d = t.decidi(PNG, nome)
    assert d.azione == t.RIFIUTA and d.travestito and "inversione_testo" in d.motivi
    assert "\u202e" not in d.nome and "\u2066" not in d.nome


def test_script_per_nome_anche_se_testo():
    d = t.decidi(b"@echo off\r\ndel *.*", "pulizia.bat")
    assert d.azione == t.RIFIUTA and "eseguibile" in d.motivi


def test_pdf_audio_video_office_archivi_solo_scheda():
    for dati, nome in [(PDF, "a.pdf"), (MP3, "a.mp3"), (MP4, "a.mp4"), (DOCX, "a.docx"), (ZIP, "a.zip"), (RAR, "a.rar")]:
        d = t.decidi(dati, nome)
        assert d.azione == t.SCHEDA, nome
        assert d.sha256 == hashlib.sha256(dati).hexdigest()


def test_pdf_con_nome_immagine_e_travestito():
    d = t.decidi(PDF, "foto.png")
    assert d.azione == t.RIFIUTA and d.travestito


def test_audio_video_e_office_archivio_sono_compatibili():
    assert not t.decidi(M4A, "a.mp4").travestito
    assert not t.decidi(MP4, "a.mp3").travestito
    assert not t.decidi(DOCX, "a.zip").travestito
    assert not t.decidi(ZIP, "a.docx").travestito


def test_html_svg_si_rifiutano_testo_e_scheda():
    assert t.decidi(HTML, "pagina.html").azione == t.RIFIUTA
    assert t.decidi(SVG, "logo.svg").azione == t.RIFIUTA
    assert t.decidi(HTML, "nota.txt").travestito
    assert t.decidi(TESTO, "nota.txt").azione == t.SCHEDA


def test_sconosciuto_si_rifiuta():
    d = t.decidi(IGNOTO, "dati.bin")
    assert d.azione == t.RIFIUTA and "sconosciuto" in d.motivi
    assert t.decidi(b"", "vuoto.png").azione == t.RIFIUTA


def test_content_type_bugiardo():
    d = t.decidi(PE, "file.bin", "image/png")
    assert d.azione == t.RIFIUTA and d.travestito


def test_senza_byte():
    assert t.decidi_senza_byte("grande.zip", None, 50_000_000).azione == t.SCHEDA
    assert t.decidi_senza_byte("grande.exe", None, 50_000_000).azione == t.RIFIUTA
    assert t.decidi_senza_byte("grande.zip", None, 50_000_000).sha256 == ""
    assert t.decidi_senza_byte("a\u202e.png", None, 5).azione == t.RIFIUTA


def test_nome_pulito():
    assert t.nome_pulito("../../etc/passwd") == "passwd"
    assert t.nome_pulito("C:\\Users\\x\\foto.png") == "foto.png"
    assert t.nome_pulito("a\x00b\x1f.png") == "ab.png"
    assert t.nome_pulito("fo\u202eto.png") == "foto.png"
    assert t.nome_pulito("") == "file" and t.nome_pulito("...") == "file" and t.nome_pulito(None) == "file"
    assert t.nome_pulito('a"b<c>.png') == "abc.png"
    lungo = t.nome_pulito("x" * 300 + ".png")
    assert len(lungo) <= t.MAX_NOME and lungo.endswith(".png")


def test_riga_scheda_e_avviso():
    d = t.decidi(DOCX, "relazione.docx")
    riga = t.riga_scheda(d)
    assert "relazione.docx" in riga and "office" in riga and d.sha256[:12] in riga
    r = t.decidi(PE, "foto.png")
    assert "foto.png" in t.riga_avviso(r) and "tipo_non_coincide" in t.riga_avviso(r)


def test_modmail_elenco_allegati_senza_link_pericolosi_e_senza_inversioni():
    from core.modmail_logic import elenco_allegati

    righe = elenco_allegati([
        ("foto.png", "https://cdn.discordapp.com/a"), ("setup.exe", "https://cdn.discordapp.com/b"),
        ("a‮gpj.png", "https://cdn.discordapp.com/c"), ("foto.png.scr", "https://cdn.discordapp.com/d"),
    ]).split("\n")
    assert righe[0] == "[foto.png](https://cdn.discordapp.com/a)"
    assert "cdn.discordapp.com/b" not in righe[1] and "setup.exe" in righe[1]
    assert righe[2] == "`agpj.png` (⚠️)"  # inversione di testo: nome pulito e niente link
    assert "cdn.discordapp.com/d" not in righe[3]


# ----------------------------- dopo la revisione -----------------------------
def test_nome_pulito_senza_accenti_gravi_e_markdown():
    """Il nome finisce tra `accenti gravi` nei log: non deve poter uscire e scrivere un link o una menzione."""
    nome = t.nome_pulito("a` [premi qui](https://esempio.test) @everyone `.txt")
    assert "`" not in nome and "](" not in nome and "@everyone" not in nome


def test_estensione_nascosta_da_caratteri_invisibili_o_larghi():
    for nome in ("fattura.e\u200bxe", "fattura.ｅｘｅ", "fattura.EXE ", "fattura.exe."):
        assert t.decidi(b"ciao", nome).azione == t.RIFIUTA, nome


@pytest.mark.parametrize("nome", ["aiuto.chm", "x.scf", "a.jnlp", "a.vhd", "a.img", "a.settingcontent-ms", "a.desktop", "a.webloc"])
def test_altre_estensioni_pericolose(nome):
    assert t.decidi(b"ciao", nome).azione == t.RIFIUTA
    assert t.decidi_senza_byte(nome, None, 10).azione == t.RIFIUTA
