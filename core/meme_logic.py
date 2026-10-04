"""
core/meme_logic.py
======================
Generatore di meme in stile classico "top text / bottom text"
(SPEC.md §16.3) — testo bianco con contorno nero, come i meme
storici di Impact. Font di default di Pillow (`ImageFont.load_
default(size=...)`, disponibile da Pillow 10.1+): niente file .ttf
da incorporare nel repository, stesso principio già seguito da
core/server_stats_image.py (evitare dipendenze/asset aggiuntivi
quando il font di sistema di Pillow basta). L'immagine di partenza
passa da core.safe_image.safe_open_image (SEC-11, SEC-20): le
dimensioni dichiarate vengono controllate prima di decodificare i
pixel e l'immagine arriva già ridotta a 2048 px di lato massimo.
Funzioni coperte: SPEC.md §16.3, REVIEW.md SEC-11, SEC-20
"""

from __future__ import annotations

import io
import textwrap

from PIL import Image, ImageDraw, ImageFont

from core.safe_image import safe_open_image

FONT_SIZE_RATIO = 12  # dimensione font = altezza immagine / questo valore
OUTLINE_WIDTH = 2
MAX_CHARS_PER_LINE = 20


def _load_image(image_bytes: bytes) -> Image.Image | None:
    try:
        # SEC-11/SEC-20: safe_open_image rifiuta le immagini con troppi
        # pixel dichiarati (ImmagineTroppoGrande, presa dal catch ampio
        # sotto come qualunque altra immagine non valida) e restituisce
        # l'immagine già ridotta a 2048 px di lato massimo, PRIMA di
        # qualsiasi filtro.
        img = safe_open_image(image_bytes)
    except Exception:
        return None

    return img.convert("RGB")


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font
) -> None:
    x, y = xy
    for dx in (-OUTLINE_WIDTH, 0, OUTLINE_WIDTH):
        for dy in (-OUTLINE_WIDTH, 0, OUTLINE_WIDTH):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill="black", anchor="mm")
    draw.text((x, y), text, font=font, fill="white", anchor="mm")


def render_meme(image_bytes: bytes, top_text: str = "", bottom_text: str = "") -> bytes | None:
    """
    Testo in alto e/o in basso, centrato orizzontalmente, andato a
    capo automaticamente se troppo lungo per una riga. Restituisce
    None se l'immagine non è apribile — mai un'eccezione che
    interromperebbe il comando con un errore poco chiaro.
    """
    img = _load_image(image_bytes)
    if img is None:
        return None

    draw = ImageDraw.Draw(img)
    dimensione_font = max(16, img.height // FONT_SIZE_RATIO)
    font = ImageFont.load_default(size=dimensione_font)

    if top_text:
        righe = textwrap.wrap(top_text.upper(), width=MAX_CHARS_PER_LINE) or [""]
        for indice, riga in enumerate(righe):
            y = dimensione_font * (indice + 1)
            _draw_outlined_text(draw, (img.width / 2, y), riga, font)

    if bottom_text:
        righe = textwrap.wrap(bottom_text.upper(), width=MAX_CHARS_PER_LINE) or [""]
        for indice, riga in enumerate(reversed(righe)):
            y = img.height - dimensione_font * (indice + 1)
            _draw_outlined_text(draw, (img.width / 2, y), riga, font)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
