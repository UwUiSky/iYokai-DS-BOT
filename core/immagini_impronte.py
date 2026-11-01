"""
core/immagini_impronte.py
=========================
Impronta percettiva delle immagini (dHash a 64 bit, scritta a mano con Pillow) e distanza tra
impronte. Si usa `tobytes()` e non `getdata()`, che sparisce con Pillow 14. Gira nel processo
figlio della sandbox, mai nel bot.
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

from PIL import Image

LATO_HASH = 8
DISTANZA_UGUALE = 4  # fino a qui e' la stessa immagine (ridimensionata, ricompressa)
DISTANZA_SIMILE = 8  # fino a qui e' «simile»: solo avviso allo staff


def dhash(img: Image.Image) -> int:
    """64 bit: per ogni riga di 8 punti, 1 se un punto e' piu' chiaro del suo vicino a destra."""
    piccola = img.convert("L").resize((LATO_HASH + 1, LATO_HASH), Image.BILINEAR)
    px = piccola.tobytes()
    valore = 0
    for y in range(LATO_HASH):
        riga = y * (LATO_HASH + 1)
        for x in range(LATO_HASH):
            valore = (valore << 1) | (1 if px[riga + x] > px[riga + x + 1] else 0)
    return valore


def distanza(a: int, b: int) -> int:
    """Bit diversi tra due impronte."""
    return (a ^ b).bit_count()


def esito_distanza(d: int) -> str:
    """`uguale`, `simile` oppure `diversa`."""
    if d <= DISTANZA_UGUALE:
        return "uguale"
    return "simile" if d <= DISTANZA_SIMILE else "diversa"
