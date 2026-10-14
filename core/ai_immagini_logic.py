"""
core/ai_immagini_logic.py
=========================
Ingrandimento e pulizia di un'immagine sulla macchina del bot (Pillow):
serve per l'immagine appena generata e per quelle caricate dagli utenti,
anche senza un servizio AI di ingrandimento. Il risultato resta sotto
il limite di 10 MiB degli allegati.
Funzioni coperte: SPEC §25.61, §25.62 (AI-R-067, AI-R-068; catalogo AI-006, AI-007)
"""

from __future__ import annotations

import io

from PIL import Image, ImageFilter, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_LATO = 4096
MAX_PIXEL_INGRESSO = 4096 * 4096


class ImmagineNonValida(ValueError):
    pass


def ingrandisci(dati: bytes, fattore: int = 2) -> tuple[bytes, str]:
    """
    (byte, estensione). Ingrandisce di `fattore` (senza superare MAX_LATO per lato),
    toglie il rumore leggero e rende più nitidi i bordi. PNG se entra, altrimenti JPEG.
    """
    try:
        img = Image.open(io.BytesIO(dati))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImmagineNonValida("Il file non è un'immagine leggibile.") from exc
    if img.width * img.height > MAX_PIXEL_INGRESSO:
        raise ImmagineNonValida("Immagine troppo grande da ingrandire.")
    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    scala = max(1.0, min(fattore, MAX_LATO / img.width, MAX_LATO / img.height))
    nuova = img.resize((round(img.width * scala), round(img.height * scala)), Image.LANCZOS)
    nuova = nuova.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))
    uscita = io.BytesIO()
    nuova.save(uscita, format="PNG", optimize=True)
    if uscita.tell() <= MAX_BYTES:
        return uscita.getvalue(), "png"
    for qualita in (92, 85, 75, 60):
        uscita = io.BytesIO()
        nuova.convert("RGB").save(uscita, format="JPEG", quality=qualita)
        if uscita.tell() <= MAX_BYTES:
            return uscita.getvalue(), "jpg"
    raise ImmagineNonValida("Il risultato supera i 10 MiB.")
