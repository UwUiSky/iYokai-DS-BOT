"""
tests/support/conversioni_finte.py
==================================
File veri per i test delle conversioni (D74, #160): PDF con JavaScript e file incorporato fatti con pypdf, audio e
video generati con ffmpeg `lavfi`, sonda con ffprobe. Nessun file di prova nel repository.
Funzioni coperte: SPEC §8.16 (D74, #160)
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path


def pdf_pericoloso(pagine: int = 2) -> bytes:
    """PDF con JavaScript, azione all'apertura, file incorporato, link con URI, azioni di pagina e metadati."""
    from pypdf import PdfWriter
    from pypdf.annotations import Link
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject

    w = PdfWriter()
    for _ in range(pagine):
        w.add_blank_page(200, 200)
    from pypdf.generic import ArrayObject

    js = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("app.alert('ciao');")})
    w._root_object[NameObject("/Names")] = DictionaryObject({
        NameObject("/JavaScript"): DictionaryObject({NameObject("/Names"): ArrayObject([TextStringObject("a"), w._add_object(js)])})
    })
    w.add_attachment("nascosto.txt", b"segreto")
    w.add_metadata({"/Title": "titolo segreto", "/Author": "autore segreto"})
    w.add_annotation(page_number=0, annotation=Link(rect=(10, 10, 50, 50), url="http://example.invalid/x"))
    azione = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("app.alert(2)")})
    w._root_object[NameObject("/OpenAction")] = azione
    w._root_object[NameObject("/AA")] = DictionaryObject({NameObject("/WC"): azione})
    w.pages[0][NameObject("/AA")] = DictionaryObject({NameObject("/O"): azione})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def pdf_semplice(pagine: int = 3) -> bytes:
    from pypdf import PdfWriter

    w = PdfWriter()
    for _ in range(pagine):
        w.add_blank_page(100, 100)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def pdf_con_testo(testo: str = "Ciao yokai") -> bytes:
    """PDF a mano con una pagina di testo vero (carattere Helvetica) e un'annotazione di evidenziazione senza azioni."""
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject, NumberObject

    w = PdfWriter()
    pagina = w.add_blank_page(200, 200)
    flusso = DecodedStreamObject()
    flusso.set_data(f"BT /F1 18 Tf 20 100 Td ({testo}) Tj ET".encode())
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    pagina[NameObject("/Contents")] = w._add_object(flusso)
    pagina[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(font)})})
    evidenzia = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Highlight"),
        NameObject("/Rect"): ArrayObject([FloatObject(20), FloatObject(95), FloatObject(120), FloatObject(115)]),
        NameObject("/QuadPoints"): ArrayObject([FloatObject(v) for v in (20, 115, 120, 115, 20, 95, 120, 95)]),
        NameObject("/F"): NumberObject(4),
    })
    pagina[NameObject("/Annots")] = ArrayObject([w._add_object(evidenzia)])
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def pdf_cifrato() -> bytes:
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(100, 100)
    w.encrypt("segreta")
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _ffmpeg(cartella: Path, nome: str, *argv: str) -> bytes:
    percorso = cartella / nome
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", *argv, str(percorso)], check=True, stdin=subprocess.DEVNULL, timeout=120
    )
    return percorso.read_bytes()


def audio(cartella: Path, secondi: float = 2, canali: int = 1, formato: str = "wav", titolo: str = "titolo segreto") -> bytes:
    """Un tono generato da ffmpeg; `formato` e' l'estensione del contenitore (wav, flac, mp3, ogg)."""
    ingresso = ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=16000:duration={secondi}", "-ac", str(canali)]
    return _ffmpeg(cartella, f"in.{formato}", *ingresso, "-metadata", f"title={titolo}", "-metadata", "artist=autore segreto")


def video(cartella: Path, secondi: float = 2, larghezza: int = 1920, altezza: int = 1080, con_audio: bool = True, rate: int = 25) -> bytes:
    argv = ["-f", "lavfi", "-i", f"testsrc=duration={secondi}:size={larghezza}x{altezza}:rate={rate}"]
    if con_audio:
        argv += ["-f", "lavfi", "-i", f"sine=frequency=330:duration={secondi}", "-c:a", "aac", "-shortest"]
    argv += ["-c:v", "libx264", "-preset", "ultrafast", "-metadata", "title=titolo segreto", "-metadata", "comment=nascosto"]
    return _ffmpeg(cartella, "in.mp4", *argv)


def sonda(percorso: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(percorso)],
        check=True, capture_output=True, timeout=60,
    )
    return json.loads(r.stdout)
