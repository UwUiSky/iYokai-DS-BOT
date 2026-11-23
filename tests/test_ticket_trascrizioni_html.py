"""
tests/test_ticket_trascrizioni_html.py
======================================
TKT-072 (D111): trascrizione HTML dei ticket. Orario con i secondi, autore pulito, testo escapato, immagini solo come
PNG ricodificato incorporato, gli altri allegati solo come nome, tipo e peso, tetto per immagine e tetto del file.
"""

import re
from datetime import datetime, timezone

from core import ticket_transcript_logic as tr
from core.ticket_transcript_logic import AllegatoT, IntestazioneT, MessaggioT

H = IntestazioneT(3, (("Categoria", "Aiuto"),), None)
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 100


def test_orario_con_i_secondi():
    assert tr.ora_completa(datetime(2026, 11, 23, 9, 5, 7, tzinfo=timezone.utc)) == "2026-11-23 09:05:07"
    pagina = tr.html_in_parti(H, [MessaggioT("2026-11-23 09:05:07", "mario", "ciao")])[0]
    assert "09:05:07" in pagina


def test_autore_senza_caratteri_di_controllo_e_inversioni():
    assert tr.nome_autore("ma‮rio\x00​ <b>") == "mario <b>"
    assert tr.nome_autore("   ") == "?"


def test_messaggio_con_script_resta_testo():
    m = MessaggioT("10:00:00", "<script>x()</script>", "<script>alert(1)</script> https://truffa.example/a")
    pagina = tr.html_in_parti(H, [m])[0]
    assert "<script" not in pagina
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in pagina
    assert "<a " not in pagina and "href=" not in pagina  # nessun link cliccabile


def test_immagine_incorporata_solo_come_png_ricodificato():
    m = MessaggioT("10:00:00", "mario", "", (AllegatoT("foto.jpg", 999999, "ab" * 32, PNG, "image/jpeg"),))
    pagina = tr.html_in_parti(H, [m])[0]
    assert pagina.count("data:image/png;base64,") == 1
    assert not re.search(r'src="(?!data:image/png;base64,)', pagina)
    # senza copia ricodificata: niente immagine, solo il nome
    senza = tr.html_in_parti(H, [MessaggioT("10:00:00", "m", "", (AllegatoT("foto.jpg", 5, "cd", b"", "image/jpeg"),))])[0]
    assert "<img" not in senza and "foto.jpg" in senza


def test_zip_e_video_solo_nome_tipo_e_peso():
    allegati = (
        AllegatoT("archivio.zip", 2048, "ee" * 32, b"", "application/zip"),
        AllegatoT("clip.mp4", 5_000_000, "ff" * 32, b"", "video/mp4"),
    )
    pagina = tr.html_in_parti(H, [MessaggioT("10:00:00", "mario", "", allegati)])[0]
    assert "archivio.zip" in pagina and "application/zip" in pagina and "2048 byte" in pagina
    assert "clip.mp4" in pagina and "video/mp4" in pagina
    assert "<img" not in pagina and "<a " not in pagina and "href" not in pagina and "<video" not in pagina


def test_tetto_per_immagine_e_totale():
    grande = b"\x89PNG" + b"y" * (tr.MAX_BYTE_IMMAGINE + 1)
    piccola = b"\x89PNG" + b"z" * 1000
    m = MessaggioT("10:00:00", "m", "", (AllegatoT("a.png", 1, "aa", grande, "image/png"), AllegatoT("b.png", 1, "bb", piccola, "image/png")))
    pagina = tr.html_in_parti(H, [m])[0]
    assert pagina.count("<img") == 1 and "a.png" in pagina  # la grande resta solo nome
    # tetto del file: le immagini che non entrano restano nome, il file non supera il tetto
    messaggi = [
        MessaggioT("10:00:00", "m", "", (AllegatoT(f"i{n}.png", 1, "aa", b"\x89PNG" + bytes([n]) * 900_000, "image/png"),))
        for n in range(1, 21)
    ]
    parti = tr.html_in_parti(H, messaggi, max_byte=3 * 1024 * 1024)
    assert len(parti) == 1 and len(parti[0].encode()) <= 3 * 1024 * 1024
    assert 0 < parti[0].count("<img") < 20
    assert "i20.png" in parti[0]
