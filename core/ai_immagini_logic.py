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

from core.safe_image import ImmagineTroppoGrande, apri_in_sandbox

MAX_BYTES = 10 * 1024 * 1024
MAX_LATO = 4096


class ImmagineNonValida(ValueError):
    pass


MAX_BYTES_INVIO = int(9.5 * 1024 * 1024)  # D74: file inviati sotto 9,5 MiB


def ripulisci(dati: bytes) -> bytes:
    """
    AI-004: l'immagine generata si controlla DOPO (è davvero un'immagine, pixel entro il limite) e si
    ricodifica in PNG dai soli pixel (via ogni metadato). Sopra 9,5 MiB non si manda.
    """
    try:
        img = apri_in_sandbox(dati, max_side=MAX_LATO)
    except ImmagineTroppoGrande as exc:
        raise ImmagineNonValida("Immagine troppo grande.") from exc
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImmagineNonValida("Il file non è un'immagine leggibile.") from exc
    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    uscita = io.BytesIO()
    img.save(uscita, format="PNG", optimize=True)
    if uscita.tell() > MAX_BYTES_INVIO:
        raise ImmagineNonValida("Immagine troppo pesante da mandare.")
    return uscita.getvalue()


def ingrandisci(dati: bytes, fattore: int = 2) -> tuple[bytes, str]:
    """
    (byte, estensione). Lavoro pesante per la CPU: dai cog si chiama in un thread. Ingrandisce di `fattore` (senza superare MAX_LATO per lato),
    toglie il rumore leggero e rende più nitidi i bordi. PNG se entra, altrimenti JPEG.
    """
    try:
        # Punto unico (core/safe_image.py): formati ammessi, pixel controllati prima di decodificare.
        img = apri_in_sandbox(dati, max_side=MAX_LATO)
    except ImmagineTroppoGrande as exc:
        raise ImmagineNonValida("Immagine troppo grande da ingrandire.") from exc
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImmagineNonValida("Il file non è un'immagine leggibile.") from exc
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
