"""
core/ruoli_immagini.py
======================
Dall'immagine arrivata da fuori (allegato o indirizzo) alla copia da salvare: aperta solo con le regole di
core/safe_image.py (formati, 16 megapixel, lato massimo) e ricodificata. L'originale non si conserva (D74).
Funzioni coperte: SPEC RUO-012, RUO-053
"""

from __future__ import annotations

import io

from PIL import Image

from core.safe_image import safe_open_image

MAX_BYTE_COPIA = 3 * 1024 * 1024
LATO_MENU = 1280


def ricodifica_per_menu(dati: bytes) -> bytes:
    """
    PNG rifatto da zero (niente metadati dell'originale); se pesa troppo diventa JPEG, più piccolo se serve.
    Solleva ImmagineTroppoGrande, UnidentifiedImageError o ValueError (resta troppo pesante).
    """
    immagine = safe_open_image(dati)
    immagine.thumbnail((LATO_MENU, LATO_MENU))
    if immagine.mode not in ("RGB", "RGBA"):
        immagine = immagine.convert("RGBA" if "A" in immagine.getbands() else "RGB")
    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG", optimize=True)
    if buffer.tell() <= MAX_BYTE_COPIA:
        return buffer.getvalue()
    rgb = immagine.convert("RGB")
    for qualita in (88, 75, 60):
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=qualita)
        if buffer.tell() <= MAX_BYTE_COPIA:
            return buffer.getvalue()
    raise ValueError("L'immagine resta troppo pesante anche ricompressa.")
