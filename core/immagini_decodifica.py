"""
core/immagini_decodifica.py
===========================
Apertura di un'immagine con Pillow: gira SOLO dentro il processo figlio della sandbox (`core/immagini_worker.py`),
mai nel bot (un test lo controlla). Controlla larghezza x altezza PRIMA di decodificare i pixel e riduce subito
l'immagine al lato massimo, cosi' ogni filtro lavora su un'immagine piccola (SEC-11, SEC-20).
Funzioni coperte: REVIEW.md SEC-11, SEC-20; SPEC §6 (D62)
Dipende da: core/safe_image.py (i limiti)
"""

from __future__ import annotations

import io

from PIL import Image

from core.safe_image import DIVISORE_PIXEL_DECODIFICA_PESANTE, FORMATI_AMMESSI, MAX_PIXELS, MAX_SIDE, ImmagineTroppoGrande

# Per ridurre un'immagine con trasparenza Pillow lavora su una copia "premoltiplicata" e tiene in memoria anche
# l'originale per tutto il ridimensionamento: si fa la copia da se' e si lascia andare subito l'originale.
_PREMOLTIPLICATO = {"RGBA": "RGBa", "LA": "La"}


def _limite_pixel(img: Image.Image, max_pixels: int) -> int:
    decodifica_pesante = img.format in ("WEBP", "AVIF", "HEIF") or bool(img.info.get("progressive"))
    if decodifica_pesante:
        return max_pixels // DIVISORE_PIXEL_DECODIFICA_PESANTE
    return max_pixels


def safe_open_image(
    image_bytes: bytes, max_pixels: int = MAX_PIXELS, max_side: int = MAX_SIDE, formati: tuple[str, ...] = FORMATI_AMMESSI,
) -> Image.Image:
    """
    Apre l'immagine controllando larghezza × altezza PRIMA di
    decodificare i pixel: se superano il limite solleva
    ImmagineTroppoGrande senza allocare nulla. Altrimenti restituisce
    l'immagine caricata, con il lato più lungo ridotto a max_side.
    Un formato fuori da `formati` (di norma FORMATI_AMMESSI) solleva UnidentifiedImageError.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes), formats=formati)
    except Image.DecompressionBombError as errore:
        # Oltre il doppio di Image.MAX_IMAGE_PIXELS è Pillow stesso a
        # rifiutare, già in apertura.
        raise ImmagineTroppoGrande(str(errore)) from errore

    larghezza, altezza = img.size
    limite = _limite_pixel(img, max_pixels)
    if larghezza * altezza > limite:
        raise ImmagineTroppoGrande(
            f"Immagine {img.format} {larghezza}x{altezza} "
            f"({larghezza * altezza} pixel) supera il limite di {limite} pixel."
        )
    # Solo JPEG: il decoder riduce già in lettura (1/2, 1/4, 1/8, mai
    # sotto max_side), senza allocare l'immagine intera. Per gli altri
    # formati draft() non fa nulla.
    img.draft(None, (max_side, max_side))
    img.load()
    if max(img.size) <= max_side:
        return img

    modo = img.mode
    if modo in _PREMOLTIPLICATO:
        # Riassegnando `img` l'originale viene liberato subito.
        img = img.convert(_PREMOLTIPLICATO[modo])
    img.thumbnail((max_side, max_side))
    return img.convert(modo) if img.mode != modo else img
