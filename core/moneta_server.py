"""
core/moneta_server.py
=====================
Immagine della moneta del server: preparazione dell'allegato, moneta di
base di iYokai e forma unica con cui compare negli embed dell'economia
(miniatura, file `moneta.png`).
Funzioni coperte: D38
Dipende da: core/safe_image.py
"""

from __future__ import annotations

import io
from pathlib import Path

import discord
from PIL import Image, ImageOps

from core.safe_image import safe_open_image

LATO_MONETA = 128
MAX_BYTE_MONETA = 65536
NOME_FILE_MONETA = "moneta.png"
PERCORSO_MONETA_BASE = Path(__file__).resolve().parent.parent / "assets" / "moneta_iyokai.png"


class MonetaNonValida(Exception):
    """L'immagine scelta come moneta non si può usare."""


def prepara_moneta(image_bytes: bytes) -> bytes:
    """Ritaglia al centro a quadrato, riduce a LATO_MONETA e salva PNG sotto MAX_BYTE_MONETA."""
    try:
        originale = safe_open_image(image_bytes)
        immagine = ImageOps.fit(originale.convert("RGBA"), (LATO_MONETA, LATO_MONETA), Image.LANCZOS)
    except Exception as errore:  # formato non ammesso, file rotto, troppi pixel
        raise MonetaNonValida(str(errore)) from errore
    for colori in (None, 128, 32):
        da_salvare = immagine if colori is None else immagine.quantize(colori, method=Image.FASTOCTREE)
        buffer = io.BytesIO()
        da_salvare.save(buffer, format="PNG", optimize=True)
        if buffer.tell() <= MAX_BYTE_MONETA:
            return buffer.getvalue()
    raise MonetaNonValida("Immagine troppo pesante anche dopo la riduzione.")


def moneta_base() -> bytes:
    """La moneta di iYokai (PNG nel repository)."""
    return PERCORSO_MONETA_BASE.read_bytes()


def aggiungi_moneta(embed: discord.Embed, immagine: bytes | None) -> discord.File:
    """
    Mette la moneta come miniatura dell'embed (è l'unica forma usata ovunque)
    e restituisce il file da allegare alla risposta: `file=...`.
    """
    embed.set_thumbnail(url=f"attachment://{NOME_FILE_MONETA}")
    return discord.File(io.BytesIO(immagine or moneta_base()), filename=NOME_FILE_MONETA)
