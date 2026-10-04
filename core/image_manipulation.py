"""
core/image_manipulation.py
==============================
Elaborazione VERA dei byte dell'immagine per SPEC.md §16.2 (Image
manipulation) — stesso principio di core/image_thumbnail.py: Pillow
è sincrono e CPU-bound, il chiamante (il cog) la esegue tramite
core.safe_image.run_image_task, non qui dentro. Ogni funzione
restituisce None (non solleva) se l'immagine non è apribile da
Pillow, incluso un file piccolo con dimensioni dichiarate enormi
(SEC-11, vedi core/safe_image.py) — un allegato del genere non deve
far fallire il comando con un errore poco chiaro, solo restituire
"non è stato possibile elaborare questa immagine". I filtri lavorano
sempre su un'immagine già ridotta a 2048 px di lato massimo (SEC-20).
Funzioni coperte: SPEC.md §16.2, REVIEW.md SEC-11, SEC-20
"""

from __future__ import annotations

import io

from PIL import Image, ImageFilter, ImageOps

from core.safe_image import safe_open_image


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


def _encode_png(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def apply_grayscale(image_bytes: bytes) -> bytes | None:
    img = _load_image(image_bytes)
    if img is None:
        return None
    return _encode_png(ImageOps.grayscale(img).convert("RGB"))


def apply_invert(image_bytes: bytes) -> bytes | None:
    img = _load_image(image_bytes)
    if img is None:
        return None
    return _encode_png(ImageOps.invert(img))


def apply_blur(image_bytes: bytes, radius: int = 8) -> bytes | None:
    img = _load_image(image_bytes)
    if img is None:
        return None
    radius = max(1, min(radius, 50))
    return _encode_png(img.filter(ImageFilter.GaussianBlur(radius=radius)))


def apply_pixelate(image_bytes: bytes, block_size: int = 16) -> bytes | None:
    """
    Rimpicciolisce l'immagine con un filtro NEAREST (niente
    interpolazione, così i blocchi restano netti) e poi la riporta
    alla dimensione originale con lo stesso filtro — è la tecnica
    standard per un effetto "pixelato" senza librerie aggiuntive.
    """
    img = _load_image(image_bytes)
    if img is None:
        return None

    block_size = max(2, min(block_size, 100))
    larghezza_piccola = max(1, img.width // block_size)
    altezza_piccola = max(1, img.height // block_size)

    piccola = img.resize((larghezza_piccola, altezza_piccola), resample=Image.NEAREST)
    pixelata = piccola.resize(img.size, resample=Image.NEAREST)
    return _encode_png(pixelata)
