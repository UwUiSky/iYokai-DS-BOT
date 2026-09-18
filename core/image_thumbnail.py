"""
core/image_thumbnail.py
==========================
Elaborazione VERA dei byte dell'immagine — a differenza di
core/image_thumbnail_logic.py (solo decisioni pure), questo modulo
usa Pillow per aprire, ridimensionare e ri-codificare un'immagine da
zero. Il punto centrale del perché questo esiste: il file
RIGENERATO non è mai il file originale ricaricato — viene decodificato
in memoria e ricreato pixel per pixel, il che elimina automaticamente
qualunque metadato originale (EXIF con posizione GPS, informazioni
del dispositivo, ecc.) senza doverlo ripulire esplicitamente.
"""

from __future__ import annotations

import io
import logging

from PIL import Image

from core.image_thumbnail_logic import THUMBNAIL_MAX_DIMENSION

logger = logging.getLogger("iyokai.image_thumbnail")


def generate_thumbnail(image_bytes: bytes, max_dimension: int = THUMBNAIL_MAX_DIMENSION) -> bytes | None:
    """
    Apre l'immagine, la ridimensiona mantenendo le proporzioni (il
    lato più lungo non supera max_dimension), e la ri-codifica in
    WebP — formato compatto, adatto ad essere incorporato come data
    URI senza appesantire troppo il file HTML finale.

    Restituisce None (non solleva) se l'immagine non è apribile da
    Pillow: un file con estensione .png che in realtà non è
    un'immagine valida (o è corrotto) non deve far fallire l'intera
    generazione del transcript, solo saltare quella singola
    thumbnail.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Le GIF animate e i PNG con trasparenza vanno convertiti
            # esplicitamente: RGBA per preservare la trasparenza dove
            # presente, altrimenti Pillow potrebbe sollevare in fase
            # di salvataggio WebP per certe modalità di origine (es.
            # palette "P" di una GIF).
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")

            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            output = io.BytesIO()
            img.save(output, format="WEBP", quality=80)
            return output.getvalue()
    except Exception:
        # Pillow può sollevare diversi tipi di eccezione a seconda di
        # COME il file è malformato (UnidentifiedImageError, OSError,
        # ecc.) — un catch ampio qui è intenzionale: qualunque sia il
        # motivo, il comportamento voluto è identico (salta questa
        # thumbnail, logga, continua con le altre).
        logger.warning("Impossibile generare la thumbnail per un allegato — saltato.")
        return None
