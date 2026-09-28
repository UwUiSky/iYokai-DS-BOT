"""
core/safe_image.py
======================
Punto unico per aprire in modo sicuro un'immagine arrivata da fuori
(allegato Discord, avatar) con Pillow — SEC-11: Image.open() è pigro
(legge solo l'header), ma qualunque operazione successiva che
decodifica i pixel (.load(), .thumbnail(), .resize(), ecc.) alloca
subito tutta la RAM per l'immagine intera. Un PNG da pochi MB può
dichiarare dimensioni enormi e comprimersi benissimo su disco (una
tinta unita, ad esempio) mentre decompresso arriva a centinaia di MB
di RAM — poche richieste così in parallelo bastano a far crollare
tutto il processo. safe_open_image() controlla le dimensioni
dichiarate PRIMA di chiamare .load(), così un file del genere viene
rifiutato senza mai allocare quella memoria.

Un semaforo globale limita anche a 2 le elaborazioni Pillow CPU-bound
in corso insieme in tutto il processo (non per server, non per
comando): è la RAM del processo intero il limite reale su Oracle
Free Tier.

Funzioni coperte: REVIEW.md SEC-11
"""

from __future__ import annotations

import asyncio
import io
from typing import Callable, TypeVar

from PIL import Image

# Oltre questo numero di pixel dichiarati, un'immagine viene
# rifiutata prima di essere decodificata. ~40 milioni di pixel è
# generoso per qualunque allegato/avatar legittimo (un'immagine
# 6000x6000 è già 36 milioni) mentre tiene la RAM di una singola
# decodifica RGBA sotto i ~160 MB.
MAX_PIXELS = 40_000_000

# Impostato qui, in un solo punto: Pillow stesso rifiuta di
# decodificare oltre questo limite (solleva Image.DecompressionBombError
# nei punti che non passano da safe_open_image), come seconda linea
# di difesa oltre al controllo esplicito sotto.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

# Al massimo 2 elaborazioni Pillow CPU-bound insieme, in tutto il
# processo (thumbnail della trappola anti-spam, comandi immagine di
# /fun, meme).
_SEMAPHORE = asyncio.Semaphore(2)

T = TypeVar("T")


class ImmagineTroppoGrande(Exception):
    """Le dimensioni dichiarate dall'immagine superano il limite consentito."""


def safe_open_image(image_bytes: bytes, max_pixels: int = MAX_PIXELS) -> Image.Image:
    """
    Apre l'immagine e controlla larghezza × altezza PRIMA di
    decodificare i pixel — Image.open() legge solo l'header, non
    ancora i dati veri e propri. Solleva ImmagineTroppoGrande (senza
    mai chiamare .load()) se le dimensioni dichiarate superano
    max_pixels; altrimenti carica l'immagine e la restituisce, pronta
    per essere elaborata.
    """
    img = Image.open(io.BytesIO(image_bytes))
    larghezza, altezza = img.size
    if larghezza * altezza > max_pixels:
        raise ImmagineTroppoGrande(
            f"Immagine {larghezza}x{altezza} ({larghezza * altezza} pixel) "
            f"supera il limite di {max_pixels} pixel."
        )
    img.load()
    return img


async def run_image_task(func: Callable[..., T], *args) -> T:
    """
    Esegue una funzione Pillow CPU-bound in un thread separato
    (asyncio.to_thread, come già fatto dai chiamanti prima di
    SEC-11), ma senza mai più di due esecuzioni insieme in tutto il
    processo — vedi _SEMAPHORE sopra.
    """
    async with _SEMAPHORE:
        return await asyncio.to_thread(func, *args)
