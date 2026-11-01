"""
tests/support/immagini_finte.py
===============================
Immagini costruite al volo per i test del filtro immagini (D62): valide, poliglotte,
con dati in coda, con dimensioni assurde, con QR. Nessun file di prova nel repository.
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

import io
import struct
import zlib

from PIL import Image, ImageDraw


def _salva(img: Image.Image, formato: str, **kw) -> bytes:
    buf = io.BytesIO()
    img.save(buf, formato, **kw)
    return buf.getvalue()


def png(w: int = 32, h: int = 24, colore=(200, 30, 30)) -> bytes:
    return _salva(Image.new("RGB", (w, h), colore), "PNG")


def jpeg(w: int = 64, h: int = 48, colore=(30, 120, 200)) -> bytes:
    # Un po' di disegno: un JPEG tutto uguale e' troppo regolare per i controlli di rumore.
    img = Image.new("RGB", (w, h), colore)
    ImageDraw.Draw(img).rectangle((4, 4, w // 2, h // 2), fill=(250, 250, 10))
    return _salva(img, "JPEG", quality=85)


def gif(w: int = 20, h: int = 20) -> bytes:
    return _salva(Image.new("P", (w, h), 3), "GIF")


def gif_animata(fotogrammi: int = 5) -> bytes:
    img = []
    for n in range(fotogrammi):
        fotogramma = Image.new("RGB", (16, 16), (10, 10, 10))
        ImageDraw.Draw(fotogramma).rectangle((n % 12, 0, n % 12 + 3, 15), fill=(250, 40 + n, 40))
        img.append(fotogramma)
    return _salva(img[0], "GIF", save_all=True, append_images=img[1:], duration=50, loop=0)


def webp(w: int = 40, h: int = 30) -> bytes:
    return _salva(Image.new("RGB", (w, h), (10, 200, 90)), "WEBP", lossless=True)


def mp4_finto(n_byte: int = 4000) -> bytes:
    """Una scatola `ftyp` seguita da dati: basta per sembrare la parte video di una foto in movimento."""
    ftyp = struct.pack(">I4s4sI4s4s", 24, b"ftyp", b"isom", 512, b"isom", b"mp41")
    return ftyp + struct.pack(">I4s", n_byte + 8, b"mdat") + bytes((i * 7 + 3) % 256 for i in range(n_byte))


def png_con_coda(coda: bytes) -> bytes:
    return png() + coda


def zip_finto() -> bytes:
    return b"PK\x03\x04" + b"\x14\x00" + b"\x00" * 40 + b"PK\x05\x06" + b"\x00" * 18


def eseguibile_finto() -> bytes:
    return b"MZ\x90\x00" + b"This program cannot be run in DOS mode." + b"\x00" * 60


def png_dichiarato(w: int, h: int) -> bytes:
    """PNG con intestazione valida (CRC giusti) che dichiara w x h; i dati dei pixel sono minuscoli."""

    def blocco(tipo: bytes, dati: bytes) -> bytes:
        return struct.pack(">I", len(dati)) + tipo + dati + struct.pack(">I", zlib.crc32(tipo + dati))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + blocco(b"IHDR", ihdr) + blocco(b"IDAT", zlib.compress(b"\x00")) + blocco(b"IEND", b"")


def png_crc_rotto() -> bytes:
    dati = bytearray(png())
    dati[29] ^= 0xFF  # dentro IHDR: il CRC non torna piu'
    return bytes(dati)


def jpeg_con_mp4(n_byte: int = 6000) -> bytes:
    """Foto in movimento (Google/Samsung): JPEG vero seguito da un video MP4. Il video e' piu' grande della foto."""
    return jpeg() + mp4_finto(n_byte)


def qr(testo: str, lato: int = 220) -> Image.Image:
    """Un QR vero (libreria `qrcode` non richiesta): si disegna a mano con un codificatore minimo se manca zxing."""
    import zxingcpp

    barcode = zxingcpp.create_barcode(testo, zxingcpp.BarcodeFormat.QRCode)
    img = barcode.to_image(scale=6, add_quiet_zones=True).convert("RGB")
    return img.resize((lato, lato), Image.NEAREST)


def foto_con_qr(testo: str, lato: int = 480) -> bytes:
    """Una 'foto' (sfondo a gradiente) con un QR incollato sopra, in PNG."""
    sfondo = Image.new("RGB", (lato, lato))
    px = sfondo.load()
    for x in range(lato):
        for y in range(lato):
            px[x, y] = (x * 255 // lato, y * 255 // lato, 128)
    codice = qr(testo, lato // 2)
    sfondo.paste(codice, (lato // 4, lato // 4))
    return _salva(sfondo, "PNG")
