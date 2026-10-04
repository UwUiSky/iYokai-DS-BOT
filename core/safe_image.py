"""
core/safe_image.py
======================
Punto unico per aprire in modo sicuro un'immagine arrivata da fuori
(allegato Discord, avatar) con Pillow, e per eseguire i lavori Pillow
fuori dall'event loop con un numero limitato di lavori insieme.

Quattro limiti, tutti qui (SEC-11, SEC-20):
- byte: un allegato oltre MAX_IMAGE_BYTES non va nemmeno scaricato
  (il controllo lo fa il chiamante su `attachment.size`);
- formato: solo quelli in FORMATI_AMMESSI, di cui è nota la memoria
  usata dal decoder;
- pixel dichiarati: oltre MAX_PIXELS l'immagine viene rifiutata PRIMA
  di decodificarla (Image.open() legge solo l'header);
- lato massimo: l'immagine aperta viene subito ridotta a MAX_SIDE,
  così ogni filtro lavora su un'immagine piccola.

Funzioni coperte: REVIEW.md SEC-11, SEC-20
"""

from __future__ import annotations

import asyncio
import io
from typing import Callable, TypeVar

from PIL import Image

# Oltre questa dimensione un allegato non viene scaricato.
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB

# Oltre questo numero di pixel dichiarati, un'immagine viene rifiutata
# prima di essere decodificata. 16 milioni di pixel (es. 4000x4000)
# bastano per qualunque foto o avatar e tengono la decodifica sotto i
# 64 MB (4 byte per pixel).
MAX_PIXELS = 16_000_000

# Gli unici formati che apriamo: sono quelli che Discord usa per avatar
# e anteprime, e di ognuno è stato misurato quanto costa decodificarlo.
FORMATI_AMMESSI = ("PNG", "JPEG", "GIF", "WEBP", "BMP")

# WebP e JPEG progressivi, per essere decodificati, usano da 3 a 4
# volte la memoria degli altri formati (12-16 byte per pixel invece di
# 4, misurato con Pillow 12): il loro limite di pixel è un quarto,
# così il tetto di memoria resta lo stesso.
DIVISORE_PIXEL_DECODIFICA_PESANTE = 4

# Lato più lungo dell'immagine restituita da safe_open_image.
MAX_SIDE = 2048

# Seconda linea di difesa: Pillow stesso avvisa/rifiuta oltre questo
# limite nei punti che non passano da safe_open_image.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

# Al massimo 2 lavori immagine dei comandi /fun insieme, in tutto il
# processo: il limite reale è la RAM del processo intero.
_SEMAFORO_FUN = asyncio.Semaphore(2)

# SEC-20: le miniature dello spam-trap hanno una corsia loro (un lavoro
# alla volta), così un'ondata di /fun non ritarda i ban.
_SEMAFORO_SPAM_TRAP = asyncio.Semaphore(1)

# Per ridurre un'immagine con trasparenza Pillow lavora su una copia
# "premoltiplicata" e, dentro thumbnail(), tiene in memoria anche
# l'originale per tutto il ridimensionamento. safe_open_image fa la
# copia da sé e lascia andare subito l'originale: su un'immagine RGBA
# da 16 megapixel il picco scende da circa 170 a circa 130 MB.
_PREMOLTIPLICATO = {"RGBA": "RGBa", "LA": "La"}

T = TypeVar("T")


class ImmagineTroppoGrande(Exception):
    """Le dimensioni dichiarate dall'immagine superano il limite consentito."""


def _limite_pixel(img: Image.Image, max_pixels: int) -> int:
    decodifica_pesante = img.format == "WEBP" or bool(img.info.get("progressive"))
    if decodifica_pesante:
        return max_pixels // DIVISORE_PIXEL_DECODIFICA_PESANTE
    return max_pixels


def safe_open_image(
    image_bytes: bytes, max_pixels: int = MAX_PIXELS, max_side: int = MAX_SIDE
) -> Image.Image:
    """
    Apre l'immagine controllando larghezza × altezza PRIMA di
    decodificare i pixel: se superano il limite solleva
    ImmagineTroppoGrande senza allocare nulla. Altrimenti restituisce
    l'immagine caricata, con il lato più lungo ridotto a max_side.
    Un formato fuori da FORMATI_AMMESSI solleva UnidentifiedImageError.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes), formats=FORMATI_AMMESSI)
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


async def run_image_task(func: Callable[..., T], *args) -> T:
    """
    Esegue una funzione Pillow CPU-bound in un thread separato, senza
    mai più di due esecuzioni insieme in tutto il processo. Per i
    comandi immagine di /fun.
    """
    async with _SEMAFORO_FUN:
        return await asyncio.to_thread(func, *args)


async def run_spam_trap_image_task(func: Callable[..., T], *args) -> T:
    """
    Come run_image_task, ma sulla corsia riservata allo spam-trap: non
    aspetta mai dietro i lavori dei comandi /fun.
    """
    async with _SEMAFORO_SPAM_TRAP:
        return await asyncio.to_thread(func, *args)
