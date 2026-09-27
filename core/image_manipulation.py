"""
core/image_manipulation.py
==============================
Elaborazione VERA dei byte dell'immagine per SPEC.md §16.2 (Image
manipulation) — stesso principio di core/image_thumbnail.py: Pillow
è sincrono e CPU-bound, il chiamante (il cog) lo esegue in
`asyncio.to_thread`, non qui dentro. Ogni funzione restituisce None
(non solleva) se l'immagine non è apribile da Pillow — un allegato
con estensione immagine ma contenuto corrotto non deve far fallire
il comando con un errore poco chiaro, solo restituire "non è stato
possibile elaborare questa immagine".
"""

from __future__ import annotations

import io

from PIL import Image, ImageFilter, ImageOps

MAX_INPUT_DIMENSION = 4096  # oltre non ha senso elaborare: rallenta
# solo il comando senza un beneficio visibile per un'immagine che
# verrà comunque ridimensionata da Discord in anteprima.


def _load_image(image_bytes: bytes) -> Image.Image | None:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception:
        return None

    if img.width > MAX_INPUT_DIMENSION or img.height > MAX_INPUT_DIMENSION:
        img.thumbnail((MAX_INPUT_DIMENSION, MAX_INPUT_DIMENSION))

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
